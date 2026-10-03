"""
Test estymacji wagi na nagranym wideo — Podejscie3 (YOLO-seg).

    python check/test.py
"""
import json
import sys
import time
from pathlib import Path

import cv2
import numpy as np

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from detector import detect_best_pig, estimate_weight, WeightSmoother

CALIB_PATH = ROOT / "calibration.json"
COEFF_PATH = ROOT / "weight_coeff.json"

VIDEO_PATH = ROOT / "rgb_video.mp4"
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
    if known_kg is not None:
        print(f"Znana waga (z pliku): {known_kg} kg")
    print("\nP=pauza  Q=wyjscie  SPACE=nastepna klatka\n")

    smoother = WeightSmoother(window=30, sigma=2.0)
    all_weights: list[float] = []
    frame_idx = 0
    paused = False
    last_print = 0.0
    frame = None

    win_name = "Test wagi [Podejscie3 YOLO] — video"
    cv2.namedWindow(win_name, cv2.WINDOW_NORMAL)
    cv2.resizeWindow(win_name, 1280, 720)

    while True:
        if not paused:
            ret, frame = cap.read()
            if not ret:
                print("\nKoniec wideo.")
                break
            frame_idx += 1

        if frame is None:
            continue

        display = frame.copy()
        best, all_pigs, source = detect_best_pig(frame, scale)
        smooth_kg = smoother.value()

        for i, m in enumerate(all_pigs):
            color = (0, 255, 0) if m is best else (0, 200, 255)
            thickness = 3 if m is best else 1
            cv2.drawContours(display, [m["contour"]], -1, color, thickness)

        if best is not None:
            raw_kg = estimate_weight(best, coeffs)
            smooth_kg = smoother.add(raw_kg)
            all_weights.append(smooth_kg)

            cv2.line(display, best["axis_p1"], best["axis_p2"], (0, 0, 255), 2)
            cv2.line(display, best["width_p1"], best["width_p2"], (255, 0, 0), 2)

            cx, cy = best["center"]
            label = f"{smooth_kg:.1f} kg"
            (tw, th), _ = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, 1.8, 4)
            cv2.rectangle(display, (cx - tw // 2 - 10, cy - th - 16), (cx + tw // 2 + 10, cy + 12), (0, 0, 0), -1)
            cv2.putText(display, label, (cx - tw // 2, cy), cv2.FONT_HERSHEY_SIMPLEX, 1.8, (0, 255, 255), 4, cv2.LINE_AA)

            now = time.time()
            if now - last_print >= 0.5:
                err_str = ""
                if known_kg:
                    err = smooth_kg - known_kg
                    err_str = f"  |  blad: {err:+.1f} kg ({err / known_kg * 100:+.1f}%)"
                print(
                    f"Klatka {frame_idx}/{total_frames}: {smooth_kg:.1f} kg  "
                    f"L={best['length_cm']}cm W={best['width_cm']}cm  [{source}]{err_str}"
                )
                last_print = now
        else:
            now = time.time()
            if now - last_print >= 1.0:
                print(f"Klatka {frame_idx}/{total_frames}: BRAK [{source}]")
                last_print = now

        hud = [
            f"Klatka: {frame_idx}/{total_frames}  |  Swinie: {len(all_pigs)}  |  [{source.upper()}]",
        ]
        if best is not None:
            hud.append(f"L={best['length_cm']}cm  W={best['width_cm']}cm  A={best['area_cm2']}cm2")
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
        print(f"Podsumowanie ({len(arr)} klatek z pomiarami):")
        print(f"  Srednia:  {arr.mean():.1f} kg")
        print(f"  Mediana:  {np.median(arr):.1f} kg")
        print(f"  Min/Max:  {arr.min():.1f} / {arr.max():.1f} kg")
        print(f"  Std:      {arr.std():.1f} kg")
        if known_kg:
            err = float(np.median(arr)) - known_kg
            print(f"  Znana:    {known_kg} kg")
            print(f"  Blad:     {err:+.1f} kg ({err / known_kg * 100:+.1f}%)")
        print("=" * 50)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
