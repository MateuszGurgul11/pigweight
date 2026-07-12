"""
Test estymacji wagi na nagranym wideo z kamera.py (Podejscie1).
"""
import json
import time
from collections import deque
from pathlib import Path

import cv2
import numpy as np

SCRIPT_DIR = Path(__file__).resolve().parent
CALIB_PATH = SCRIPT_DIR / "calibration.json"
COEFF_PATH = SCRIPT_DIR / "weight_coeff.json"

VIDEO_PATH = Path(r"D:\Programowanie\WagaŚwiń\Podejscie1\dataset\pig_004\rgb_video.mp4")
KNOWN_WEIGHT_PATH = VIDEO_PATH.parent / "weight_kg.txt"


def load_calibration() -> dict:
    with open(CALIB_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


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


def segment_pig(image: np.ndarray):
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    blurred = cv2.GaussianBlur(gray, (11, 11), 0)
    _, binary = cv2.threshold(blurred, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (15, 15))
    binary = cv2.morphologyEx(binary, cv2.MORPH_CLOSE, kernel)
    binary = cv2.morphologyEx(binary, cv2.MORPH_OPEN, kernel)
    contours, _ = cv2.findContours(binary, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    if not contours:
        return None, binary
    valid = [(c, cv2.contourArea(c)) for c in contours if cv2.contourArea(c) > 2000]
    if not valid:
        return None, binary
    best_cnt = max(valid, key=lambda x: x[1])[0]
    return best_cnt, binary


def measure_pig(contour: np.ndarray, mask: np.ndarray, scale: float) -> dict | None:
    pixel_area = scale * scale
    area_cm2 = float(cv2.contourArea(contour)) * pixel_area

    ys, xs = np.nonzero(mask)
    if len(xs) < 50:
        return None

    points = np.column_stack([xs, ys]).astype(np.float64)
    mean = points.mean(axis=0)
    centered = points - mean
    cov = np.cov(centered, rowvar=False, bias=True)
    eigenvalues, eigenvectors = np.linalg.eigh(cov)
    idx = np.argsort(eigenvalues)[::-1]
    eigenvalues = eigenvalues[idx]
    eigenvectors = eigenvectors[:, idx]

    length_px = 4.0 * np.sqrt(max(0.0, eigenvalues[0]))
    width_px = 4.0 * np.sqrt(max(0.0, eigenvalues[1]))
    length_cm = length_px * scale
    width_cm = width_px * scale

    axis_vec = eigenvectors[:, 0]
    half = length_px / 2.0
    p1 = (int(mean[0] - axis_vec[0] * half), int(mean[1] - axis_vec[1] * half))
    p2 = (int(mean[0] + axis_vec[0] * half), int(mean[1] + axis_vec[1] * half))
    perp = eigenvectors[:, 1]
    hw = width_px / 2.0
    w1 = (int(mean[0] - perp[0] * hw), int(mean[1] - perp[1] * hw))
    w2 = (int(mean[0] + perp[0] * hw), int(mean[1] + perp[1] * hw))

    return {
        "area_cm2": round(area_cm2, 1),
        "length_cm": round(length_cm, 1),
        "width_cm": round(width_cm, 1),
        "center": (int(mean[0]), int(mean[1])),
        "axis_p1": p1, "axis_p2": p2,
        "width_p1": w1, "width_p2": w2,
        "contour": contour,
    }


def estimate_weight(m: dict, coeffs: dict) -> float:
    area = m["area_cm2"]
    length = m["length_cm"]
    width = m["width_cm"]
    w_area = coeffs.get("coeff_area", 0.033) * area
    w_volume = coeffs.get("coeff_volume", 0.0008) * length * width * width
    method = coeffs.get("method", "area")
    if method == "volume":
        return max(0.0, w_volume)
    if method == "combined":
        return max(0.0, (w_area + w_volume) / 2.0)
    return max(0.0, w_area)


class WeightSmoother:
    def __init__(self, window: int = 30, sigma: float = 2.0) -> None:
        self.history: deque[float] = deque(maxlen=window)
        self.sigma = sigma

    def add(self, raw_kg: float) -> float:
        self.history.append(raw_kg)
        return self.value()

    def value(self) -> float:
        if not self.history:
            return 0.0
        arr = np.array(self.history)
        if len(arr) < 3:
            return float(np.median(arr))
        median = float(np.median(arr))
        std = float(arr.std())
        if std < 0.5:
            return float(arr.mean())
        keep = np.abs(arr - median) < self.sigma * std
        if not keep.any():
            return median
        return float(arr[keep].mean())


def main() -> int:
    if not VIDEO_PATH.exists():
        print(f"BLAD: Brak pliku {VIDEO_PATH}")
        return 1

    cal = load_calibration()
    coeffs = load_coeff()
    scale = float(cal["scale_cm_per_px"])

    known_kg = None
    if KNOWN_WEIGHT_PATH.exists():
        try:
            known_kg = float(KNOWN_WEIGHT_PATH.read_text().strip())
        except ValueError:
            pass

    cap = cv2.VideoCapture(str(VIDEO_PATH))
    if not cap.isOpened():
        print(f"BLAD: Nie mozna otworzyc {VIDEO_PATH}")
        return 1

    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    fps = cap.get(cv2.CAP_PROP_FPS)
    w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    print(f"Wideo: {w}x{h}, {fps:.1f} FPS, {total_frames} klatek")
    print(f"Kalibracja: skala={scale:.6f} cm/px | metoda={coeffs['method']}")
    print(f"Wspolczynniki: area={coeffs['coeff_area']}, volume={coeffs['coeff_volume']}")
    if known_kg is not None:
        print(f"Znana waga (z pliku): {known_kg} kg")
    print("\nP=pauza  Q=wyjscie  SPACE=nastepna klatka\n")

    smoother = WeightSmoother(window=30, sigma=2.0)
    all_weights: list[float] = []
    frame_idx = 0
    paused = False
    last_print = 0.0

    win_name = "Test wagi — video playback"
    cv2.namedWindow(win_name, cv2.WINDOW_NORMAL)
    cv2.resizeWindow(win_name, 1280, 720)

    while True:
        if not paused:
            ret, frame = cap.read()
            if not ret:
                print("\nKoniec wideo.")
                break
            frame_idx += 1

        display = frame.copy()
        contour, binary = segment_pig(frame)
        m = None
        smooth_kg = smoother.value()

        if contour is not None:
            m = measure_pig(contour, binary, scale)

        if m is not None:
            raw_kg = estimate_weight(m, coeffs)
            smooth_kg = smoother.add(raw_kg)
            all_weights.append(smooth_kg)

            cv2.drawContours(display, [contour], -1, (0, 255, 0), 3)
            cv2.line(display, m["axis_p1"], m["axis_p2"], (0, 0, 255), 2)
            cv2.line(display, m["width_p1"], m["width_p2"], (255, 0, 0), 2)

            cx, cy = m["center"]
            label = f"{smooth_kg:.1f} kg"
            (tw, th), _ = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, 1.8, 4)
            cv2.rectangle(display, (cx-tw//2-10, cy-th-16), (cx+tw//2+10, cy+12), (0, 0, 0), -1)
            cv2.putText(display, label, (cx-tw//2, cy), cv2.FONT_HERSHEY_SIMPLEX, 1.8, (0, 255, 255), 4, cv2.LINE_AA)

            now = time.time()
            if now - last_print >= 0.5:
                err_str = ""
                if known_kg:
                    err = smooth_kg - known_kg
                    err_str = f"  |  blad: {err:+.1f} kg ({err/known_kg*100:+.1f}%)"
                print(f"Klatka {frame_idx}/{total_frames}: {smooth_kg:.1f} kg  "
                      f"L={m['length_cm']}cm W={m['width_cm']}cm{err_str}")
                last_print = now
        else:
            now = time.time()
            if now - last_print >= 1.0:
                print(f"Klatka {frame_idx}/{total_frames}: BRAK DETEKCJI")
                last_print = now

        hud = [f"Klatka: {frame_idx}/{total_frames}"]
        if m is not None:
            hud.append(f"L={m['length_cm']}cm  W={m['width_cm']}cm  A={m['area_cm2']}cm2")
        else:
            hud.append("Brak swini")
        if known_kg is not None:
            hud.append(f"Znana: {known_kg} kg  |  Estymacja: {smooth_kg:.1f} kg")
        if paused:
            hud.append("[PAUZA]")
        for i, txt in enumerate(hud):
            y = 30 + i * 28
            cv2.putText(display, txt, (12, y), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 0, 0), 4, cv2.LINE_AA)
            cv2.putText(display, txt, (12, y), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 0), 2, cv2.LINE_AA)

        cv2.imshow(win_name, display)
        delay = 0 if paused else max(1, int(1000 / max(fps, 1)))
        key = cv2.waitKey(delay) & 0xFF
        if key == ord("q"):
            break
        elif key == ord("p"):
            paused = not paused
        elif key == ord(" ") and paused:
            ret, frame = cap.read()
            if not ret:
                break
            frame_idx += 1

    cap.release()
    cv2.destroyAllWindows()

    if all_weights:
        arr = np.array(all_weights)
        print("\n" + "=" * 50)
        print(f"Podsumowanie ({len(arr)} klatek z waznymi pomiarami):")
        print(f"  Srednia:  {arr.mean():.1f} kg")
        print(f"  Mediana:  {np.median(arr):.1f} kg")
        print(f"  Min/Max:  {arr.min():.1f} / {arr.max():.1f} kg")
        print(f"  Std:      {arr.std():.1f} kg")
        if known_kg:
            err = float(np.median(arr)) - known_kg
            print(f"  Znana:    {known_kg} kg")
            print(f"  Blad:     {err:+.1f} kg ({err/known_kg*100:+.1f}%)")
        print("=" * 50)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
