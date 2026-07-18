"""Live podglad z OAK-D S2 + estymacja wagi swini — Podejscie3 (YOLO-seg).

Dwa zrodla obrazu:
    python live.py                 -> kamera OAK-D S2 (RGB + glebia)
    python live.py rgb_video.mp4   -> plik wideo (tylko RGB, do testow)

Sekwencja wazenia (identyczna dla obu zrodel):
    S / przycisk (GPIO 3, pin 5) — start: kalibracja skali -> pomiar
        przez MEASURE_DURATION_S sekund -> podsumowanie. Kolejne S/przycisk
        zaczyna od nowa.
    Q — wyjscie

Przycisk: GPIO 3 (pin 5) <-> przycisk <-> GND (pin 9); pull-up, aktywny LOW.

Kalibracja skali odbywa sie na poczatku kazdej sekwencji (nie ciagle):
podloga = najdalsza plaszczyzna w kadrze, wiec pomiar dziala nawet gdy
swinia czesciowo zaslania widok. Strumien glebi jest maly (640x400),
zeby nie obciazac Raspberry Pi. W trybie wideo nie ma glebi — uzywana jest
zapisana skala z calibration.json.
"""
import json
import sys
import time
from pathlib import Path

import cv2
import numpy as np

from detector import detect_best_pig, estimate_weight, WeightSmoother

try:
    from display import init_display
except Exception as _e:  # brak Pillow/modulu -> dziala bez ekranu
    print(f">>> ILI9341: modul display niedostepny ({_e}) — bez wyswietlacza")
    def init_display():
        return None

SCRIPT_DIR = Path(__file__).resolve().parent
CALIB_PATH = SCRIPT_DIR / "calibration.json"
COEFF_PATH = SCRIPT_DIR / "weight_coeff.json"

RGB_W, RGB_H = 1920, 1080
DEPTH_W, DEPTH_H = 640, 400

# Czas trwania faz sekwencji wazenia [s] — do wyregulowania (3 lub 5 s)
CALIBRATE_DURATION_S = 1.0
MEASURE_DURATION_S = 3.0

# Sanity-check kalibracji: odrzuc pomiar podlogi rozny o >25% od zapisanego
MAX_HEIGHT_DEVIATION = 0.25
MIN_FLOOR_CM, MAX_FLOOR_CM = 50.0, 400.0

# Stany sekwencji
STATE_IDLE = "idle"
STATE_CALIBRATING = "calibrating"
STATE_MEASURING = "measuring"
STATE_RESULT = "result"

WINDOW = "WagaSwin [YOLO]"

# Fizyczny przycisk startu — BCM GPIO 3 = pin fizyczny 5
# Okablowanie: pin 5 <-> przycisk <-> GND (pin 9); aktywny LOW + pull-up
BUTTON_PIN_NAME = "D3"
BUTTON_DEBOUNCE_S = 0.25


class StartButton:
    """Przycisk startu na GPIO. Bez Blinka = martwy obiekt (tylko klawisz S)."""

    def __init__(self) -> None:
        self._pin = None
        self._idle_high = True  # True = pull-up / aktywny LOW
        self._was_active = False
        self._last_fire = 0.0
        try:
            import board
            import digitalio

            pin = getattr(board, BUTTON_PIN_NAME)
            dio = digitalio.DigitalInOut(pin)
            dio.direction = digitalio.Direction.INPUT
            dio.pull = digitalio.Pull.UP
            self._pin = dio

            time.sleep(0.05)
            samples = [bool(dio.value) for _ in range(10)]
            high_n = sum(1 for s in samples if s)
            self._idle_high = high_n >= 5
            self._was_active = False
            polarity = "aktywny LOW (do GND)" if self._idle_high else "aktywny HIGH"
            print(
                f">>> Przycisk: GPIO {BUTTON_PIN_NAME} (pin 5) gotowy | "
                f"spoczynek={'HIGH' if self._idle_high else 'LOW'} | {polarity}"
            )
            if high_n == 0:
                print(">>> Przycisk: pin zawsze LOW — sprawdz czy nie jest na stale zwarty do GND")
            elif high_n == 10:
                print(
                    ">>> Przycisk: pin w spoczynku HIGH (OK). "
                    "Naciskaj — w konsoli musi pojawic sie 'NACISNIETY'"
                )
        except Exception as e:  # noqa: BLE001 — laptop / brak Blinka
            print(f">>> Przycisk: niedostepny ({type(e).__name__}: {e}) — tylko klawisz S")

    def _active(self) -> bool:
        high = bool(self._pin.value)
        return (not high) if self._idle_high else high

    def pressed(self) -> bool:
        """True raz na naciśnięcie (wejscie w stan aktywny), z debounce."""
        if self._pin is None:
            return False

        active = self._active()
        now = time.monotonic()
        fired = False
        if active and not self._was_active and (now - self._last_fire) >= BUTTON_DEBOUNCE_S:
            self._last_fire = now
            fired = True
            print(">>> Przycisk: NACISNIETY")
        self._was_active = active
        return fired

    def close(self) -> None:
        if self._pin is not None:
            try:
                self._pin.deinit()
            except Exception:  # noqa: BLE001
                pass
            self._pin = None


def load_calibration() -> dict:
    with open(CALIB_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def save_calibration(cal: dict) -> None:
    cal["timestamp"] = time.strftime("%Y-%m-%dT%H:%M:%S")
    with open(CALIB_PATH, "w", encoding="utf-8") as f:
        json.dump(cal, f, indent=2, ensure_ascii=False)


def load_coeff() -> dict:
    default = {"coeff_volume": 0.0008, "coeff_area": 0.033, "method": "area"}
    if not COEFF_PATH.is_file():
        return default
    try:
        with open(COEFF_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
        return {**default, **data}
    except (json.JSONDecodeError, OSError):
        return default


def estimate_floor_cm(depth_frame: np.ndarray) -> float | None:
    """
    Szacuje odleglosc do podlogi [cm] z mapy glebi (mm, uint16).
    Podloga = najdalsza plaszczyzna: bierzemy 95. percentyl glebi,
    a potem mediane pikseli w oknie ±5 cm wokol niego — dzieki temu
    swinia (blizej kamery) nie zaklamuje pomiaru.
    """
    valid = depth_frame[depth_frame > 0]
    if len(valid) < 500:
        return None
    p95 = float(np.percentile(valid, 95))
    floor_px = valid[np.abs(valid.astype(np.float64) - p95) < 50.0]  # ±5 cm
    if len(floor_px) < 100:
        return None
    return float(np.median(floor_px)) / 10.0


def summarize_weights(weights: list[float]) -> dict | None:
    if not weights:
        return None
    arr = np.array(weights)
    return {
        "n": len(arr),
        "mean": float(arr.mean()),
        "median": float(np.median(arr)),
        "min": float(arr.min()),
        "max": float(arr.max()),
        "std": float(arr.std()),
    }


def draw_status(frame: np.ndarray, lines: list[str], color: tuple[int, int, int]) -> None:
    for i, txt in enumerate(lines):
        y = 70 + i * 34
        cv2.putText(frame, txt, (12, y), cv2.FONT_HERSHEY_SIMPLEX, 0.9, (0, 0, 0), 5, cv2.LINE_AA)
        cv2.putText(frame, txt, (12, y), cv2.FONT_HERSHEY_SIMPLEX, 0.9, color, 2, cv2.LINE_AA)


class WeighingSession:
    """Maszyna stanow sekwencji wazenia — wspolna dla kamery i wideo."""

    def __init__(self, fx: float | None, display=None) -> None:
        self.cal = load_calibration()
        self.coeffs = load_coeff()
        self.scale = float(self.cal["scale_cm_per_px"])
        # fx z kamery pozwala przeliczyc skale z pomiaru podlogi; w trybie
        # wideo fx=None -> brak rekalibracji, uzywamy zapisanej skali.
        self.fx = fx
        self.can_recalibrate = fx is not None

        self.smoother = WeightSmoother(window=30, sigma=2.0)
        self.state = STATE_IDLE
        self.state_started = 0.0
        self.session_weights: list[float] = []
        self.floor_samples: list[float] = []
        self.result: dict | None = None
        self.calib_msg = ""
        self.last_print = 0.0

        # Ekran ILI9341 (moze byc None — wtedy tylko okno OpenCV)
        self.display = display
        self._disp_state: str | None = None
        self._disp_last = 0.0

    def start(self) -> None:
        self.smoother.clear()
        self.session_weights = []
        self.floor_samples = []
        self.result = None
        self.coeffs = load_coeff()  # swieze wspolczynniki (mogly zmienic sie w app.py)
        self.state = STATE_CALIBRATING
        self.state_started = time.time()
        print(">>> Start sekwencji: kalibracja skali...")

    def _finish_calibration(self) -> None:
        if not self.can_recalibrate:
            self.calib_msg = f"tryb wideo — zapisana skala ({self.cal['height_cm']}cm)"
            print(f">>> Kalibracja: {self.calib_msg}")
            return
        if not self.floor_samples:
            self.calib_msg = f"brak glebi — stara skala ({self.cal['height_cm']}cm)"
            print(f">>> Kalibracja: {self.calib_msg}")
            return

        new_height = float(np.median(self.floor_samples))
        old_height = float(self.cal["height_cm"])

        if not (MIN_FLOOR_CM < new_height < MAX_FLOOR_CM):
            self.calib_msg = f"pomiar {new_height:.0f}cm poza zakresem — stara skala"
            print(f">>> Kalibracja: {self.calib_msg}")
            return
        if abs(new_height - old_height) / old_height > MAX_HEIGHT_DEVIATION:
            self.calib_msg = f"pomiar {new_height:.0f}cm odbiega >25% od {old_height:.0f}cm — stara skala"
            print(f">>> Kalibracja: {self.calib_msg} (jesli kamera zostala przeniesiona, uruchom kalibracja.py)")
            return

        self.scale = new_height / self.fx
        self.cal.update({
            "height_cm": round(new_height, 1),
            "scale_cm_per_px": round(self.scale, 6),
            "px_per_cm": round(1.0 / self.scale, 2),
            "fov_width_cm": round(RGB_W * self.scale, 1),
            "fov_height_cm": round(RGB_H * self.scale, 1),
        })
        save_calibration(self.cal)
        self.calib_msg = f"podloga {new_height:.1f}cm, skala {self.scale:.6f} cm/px"
        print(f">>> Kalibracja OK: {self.calib_msg} ({len(self.floor_samples)} probek)")

    def _refresh_display(self, elapsed: float) -> None:
        """Odswieza ILI9341. Rysuje przy zmianie stanu; fazy trwajace ~5x/s."""
        if self.display is None:
            return
        now = time.time()
        changed = self.state != self._disp_state
        if self.state == STATE_IDLE:
            if changed:
                self.display.show_idle()
        elif self.state == STATE_CALIBRATING:
            if changed or now - self._disp_last >= 0.2:
                remaining = max(0.0, CALIBRATE_DURATION_S - elapsed)
                self.display.show_calibrating(remaining, len(self.floor_samples))
                self._disp_last = now
        elif self.state == STATE_MEASURING:
            if changed or now - self._disp_last >= 0.2:
                remaining = max(0.0, MEASURE_DURATION_S - elapsed)
                self.display.show_measuring(remaining, len(self.session_weights))
                self._disp_last = now
        elif self.state == STATE_RESULT:
            if changed:
                if self.result is None:
                    self.display.show_no_pig()
                else:
                    self.display.show_result(self.result, float(self.cal["height_cm"]))
        self._disp_state = self.state

    def update(self, frame: np.ndarray, depth_frame: np.ndarray | None = None) -> None:
        """Przetwarza jedna klatke: przejscia stanow, detekcja, rysowanie na frame."""
        now = time.time()
        elapsed = now - self.state_started

        # W fazie kalibracji zbieraj pomiary podlogi z glebi (tylko kamera)
        if self.state == STATE_CALIBRATING and depth_frame is not None:
            floor_cm = estimate_floor_cm(depth_frame)
            if floor_cm is not None:
                self.floor_samples.append(floor_cm)

        # Przejscia stanow
        if self.state == STATE_CALIBRATING and elapsed >= CALIBRATE_DURATION_S:
            self._finish_calibration()
            self.state = STATE_MEASURING
            self.state_started = now
            elapsed = 0.0
            print(">>> Wazenie...")
        elif self.state == STATE_MEASURING and elapsed >= MEASURE_DURATION_S:
            self.result = summarize_weights(self.session_weights)
            self.state = STATE_RESULT
            if self.result is None:
                print(">>> Koniec wazenia: brak pomiarow (nie wykryto swini)\n")
            else:
                r = self.result
                print("\n" + "=" * 50)
                print(f"Wynik wazenia ({r['n']} pomiarow):")
                print(f"  Srednia:  {r['mean']:.1f} kg")
                print(f"  Mediana:  {r['median']:.1f} kg")
                print(f"  Min/Max:  {r['min']:.1f} / {r['max']:.1f} kg")
                print(f"  Std:      {r['std']:.1f} kg")
                print(f"  Skala:    {self.calib_msg}")
                print("=" * 50)
                print("Nacisnij S / przycisk aby zwazyc ponownie.\n")

        detecting = self.state in (STATE_CALIBRATING, STATE_MEASURING)

        if detecting:
            best, all_pigs, source = detect_best_pig(frame, self.scale)

            for m in all_pigs:
                color = (0, 255, 0) if m is best else (0, 200, 255)
                thickness = 3 if m is best else 1
                cv2.drawContours(frame, [m["contour"]], -1, color, thickness)

            if best is not None:
                raw_kg = estimate_weight(best, self.coeffs)
                smooth_kg = self.smoother.add(raw_kg)
                if self.state == STATE_MEASURING:
                    self.session_weights.append(smooth_kg)

                cv2.line(frame, best["axis_p1"], best["axis_p2"], (0, 0, 255), 2)
                cv2.line(frame, best["width_p1"], best["width_p2"], (255, 0, 0), 2)

                cx, cy = best["center"]
                label = f"{smooth_kg:.1f} kg"
                (tw, th), _ = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, 1.8, 4)
                cv2.rectangle(frame, (cx-tw//2-10, cy-th-16), (cx+tw//2+10, cy+12), (0, 0, 0), -1)
                cv2.putText(frame, label, (cx-tw//2, cy), cv2.FONT_HERSHEY_SIMPLEX, 1.8, (0, 255, 255), 4, cv2.LINE_AA)

                dims = f"[{source.upper()}] L={best['length_cm']}cm  W={best['width_cm']}cm  A={best['area_cm2']}cm2  Swinie:{len(all_pigs)}"
                cv2.putText(frame, dims, (12, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 0, 0), 3, cv2.LINE_AA)
                cv2.putText(frame, dims, (12, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 0), 2, cv2.LINE_AA)

                if now - self.last_print >= 1.0:
                    print(f"Waga: {smooth_kg:.1f} kg | L={best['length_cm']}cm W={best['width_cm']}cm | swinie={len(all_pigs)} [{source}]")
                    self.last_print = now
            else:
                msg = f"Brak swini [{source}]"
                cv2.putText(frame, msg, (12, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 0, 0), 3, cv2.LINE_AA)
                cv2.putText(frame, msg, (12, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 0, 255), 2, cv2.LINE_AA)

        # Status sekwencji na ekranie
        if self.state == STATE_IDLE:
            draw_status(frame, ["Nacisnij S / przycisk aby rozpoczac"], (255, 255, 255))
        elif self.state == STATE_CALIBRATING:
            remaining = max(0.0, CALIBRATE_DURATION_S - elapsed)
            lines = [f"KALIBRACJA SKALI... {remaining:.1f} s"]
            if self.can_recalibrate:
                lines.append(f"Probki podlogi: {len(self.floor_samples)}")
            else:
                lines.append("tryb wideo — zapisana skala")
            draw_status(frame, lines, (0, 200, 255))
        elif self.state == STATE_MEASURING:
            remaining = max(0.0, MEASURE_DURATION_S - elapsed)
            draw_status(frame, [
                f"WAZENIE... {remaining:.1f} s",
                f"Pomiary: {len(self.session_weights)}",
            ], (0, 255, 0))
        elif self.state == STATE_RESULT:
            if self.result is None:
                draw_status(frame, [
                    "BRAK POMIAROW — nie wykryto swini",
                    "Nacisnij S / przycisk ponownie",
                ], (0, 0, 255))
            else:
                r = self.result
                draw_status(frame, [
                    f"WYNIK: srednia {r['mean']:.1f} kg | mediana {r['median']:.1f} kg",
                    f"Min/Max: {r['min']:.1f} / {r['max']:.1f} kg  ({r['n']} pomiarow)",
                    "Nacisnij S / przycisk aby zwazyc ponownie",
                ], (0, 255, 255))

        # Lustrzane odbicie statusu na ekranie ILI9341 (jesli podlaczony)
        self._refresh_display(elapsed)


def run_camera() -> None:
    """Zrodlo: kamera OAK-D S2 (RGB + maly strumien glebi do kalibracji skali)."""
    import depthai as dai

    pipeline = dai.Pipeline()
    cam_rgb = pipeline.create(dai.node.Camera)
    cam_rgb.build(dai.CameraBoardSocket.CAM_A)
    video_out = cam_rgb.requestOutput((RGB_W, RGB_H), type=dai.ImgFrame.Type.BGR888p)
    video_queue = video_out.createOutputQueue(maxSize=2, blocking=False)

    stereo = pipeline.create(dai.node.StereoDepth)
    stereo.build(autoCreateCameras=True, presetMode=dai.node.StereoDepth.PresetMode.ACCURACY)
    stereo.setDepthAlign(dai.CameraBoardSocket.CAM_A)
    stereo.setOutputSize(DEPTH_W, DEPTH_H)
    depth_queue = stereo.depth.createOutputQueue(maxSize=1, blocking=False)

    pipeline.start()

    # Ogniskowa fx z fabrycznej kalibracji kamery — stala, czytana raz
    device = pipeline.getDefaultDevice()
    fx = float(device.readCalibration().getCameraIntrinsics(dai.CameraBoardSocket.CAM_A, RGB_W, RGB_H)[0][0])

    session = WeighingSession(fx=fx, display=init_display())
    btn = StartButton()
    print(f"Zrodlo: kamera OAK-D S2 | podloga={session.cal['height_cm']}cm, skala={session.scale:.6f} cm/px | fx={fx:.1f}px | metoda={session.coeffs['method']}")
    print(f"Czas pomiaru: {MEASURE_DURATION_S:.0f} s (+ {CALIBRATE_DURATION_S:.0f} s kalibracji skali)")
    print("Uruchomiono kamere [YOLO-seg]. S / przycisk — start wazenia, Q — wyjscie\n")

    try:
        with pipeline:
            while pipeline.isRunning():
                key = cv2.waitKey(1) & 0xFF
                if key == ord("q"):
                    break
                if key == ord("s") or btn.pressed():
                    session.start()

                video_in = video_queue.tryGet()
                if video_in is None:
                    continue
                frame = video_in.getCvFrame()

                depth_frame = None
                if session.state == STATE_CALIBRATING:
                    depth_in = depth_queue.tryGet()
                    if depth_in is not None:
                        depth_frame = depth_in.getFrame()
                else:
                    depth_queue.tryGet()  # oprozniaj kolejke, zeby nie lezaly stare klatki

                session.update(frame, depth_frame)
                cv2.imshow(WINDOW, frame)
    finally:
        btn.close()
        cv2.destroyAllWindows()


def run_video(path: str) -> None:
    """Zrodlo: plik wideo (tylko RGB). Do testow bez kamery — glebia niedostepna."""
    video_path = Path(path)
    if not video_path.is_absolute():
        video_path = SCRIPT_DIR / video_path
    if not video_path.is_file():
        print(f"BLAD: brak pliku wideo {video_path}", file=sys.stderr)
        return

    cap = cv2.VideoCapture(str(video_path))
    if not cap.isOpened():
        print(f"BLAD: nie mozna otworzyc {video_path}", file=sys.stderr)
        return

    fps = cap.get(cv2.CAP_PROP_FPS) or 15.0
    total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    delay = max(1, int(1000 / fps))

    session = WeighingSession(fx=None, display=init_display())  # brak glebi -> zapisana skala
    btn = StartButton()
    print(f"Zrodlo: wideo {video_path.name} ({total} klatek, {fps:.0f} FPS) | skala={session.scale:.6f} cm/px | metoda={session.coeffs['method']}")
    print(f"Czas pomiaru: {MEASURE_DURATION_S:.0f} s (+ {CALIBRATE_DURATION_S:.0f} s stabilizacji)")
    print("Wideo zapetla sie. S / przycisk — start wazenia, Q — wyjscie\n")

    cv2.namedWindow(WINDOW, cv2.WINDOW_NORMAL)
    cv2.resizeWindow(WINDOW, 1280, 720)

    try:
        while True:
            key = cv2.waitKey(delay) & 0xFF
            if key == ord("q"):
                break
            if key == ord("s") or btn.pressed():
                session.start()

            ret, frame = cap.read()
            if not ret:  # koniec pliku -> zapetl
                cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
                continue

            session.update(frame, depth_frame=None)
            cv2.imshow(WINDOW, frame)
    finally:
        btn.close()
        cap.release()
        cv2.destroyAllWindows()


if __name__ == "__main__":
    if len(sys.argv) > 1:
        run_video(sys.argv[1])
    else:
        run_camera()
