"""Live podglad z OAK-D S2 + estymacja wagi swini — Podejscie3 (YOLO-seg)."""
import json
import time
from pathlib import Path

import cv2
import depthai as dai
import numpy as np

from detector import detect_best_pig, estimate_weight, WeightSmoother

SCRIPT_DIR = Path(__file__).resolve().parent
CALIB_PATH = SCRIPT_DIR / "calibration.json"
COEFF_PATH = SCRIPT_DIR / "weight_coeff.json"


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


cal = load_calibration()
coeffs = load_coeff()
scale = float(cal["scale_cm_per_px"])

pipeline = dai.Pipeline()
cam_rgb = pipeline.create(dai.node.Camera)
cam_rgb.build(dai.CameraBoardSocket.CAM_A)
video_out = cam_rgb.requestOutput((1920, 1080), type=dai.ImgFrame.Type.BGR888p)
video_queue = video_out.createOutputQueue(maxSize=2, blocking=False)

smoother = WeightSmoother(window=30, sigma=2.0)
last_print = 0.0

pipeline.start()
print(f"Kalibracja: skala={scale:.6f} cm/px | metoda={coeffs['method']}")
print(f"Wspolczynniki: area={coeffs['coeff_area']}, volume={coeffs['coeff_volume']}")
print("Uruchomiono kamere [YOLO-seg]. Q — wyjscie\n")

try:
    with pipeline:
        while pipeline.isRunning():
            video_in = video_queue.tryGet()
            if video_in is None:
                if cv2.waitKey(1) & 0xFF == ord("q"):
                    break
                continue

            frame = video_in.getCvFrame()
            best, all_pigs, source = detect_best_pig(frame, scale)

            # Rysuj wszystkie wykryte swinie
            for m in all_pigs:
                color = (0, 255, 0) if m is best else (0, 200, 255)
                thickness = 3 if m is best else 1
                cv2.drawContours(frame, [m["contour"]], -1, color, thickness)

            if best is not None:
                raw_kg = estimate_weight(best, coeffs)
                smooth_kg = smoother.add(raw_kg)

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

                now = time.time()
                if now - last_print >= 1.0:
                    print(f"Waga: {smooth_kg:.1f} kg | L={best['length_cm']}cm W={best['width_cm']}cm | swinie={len(all_pigs)} [{source}]")
                    last_print = now
            else:
                msg = f"Brak swini [{source}]"
                cv2.putText(frame, msg, (12, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 0, 0), 3, cv2.LINE_AA)
                cv2.putText(frame, msg, (12, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 0, 255), 2, cv2.LINE_AA)

            cv2.imshow("WagaSwin [YOLO] — live", frame)
            if cv2.waitKey(1) & 0xFF == ord("q"):
                break
finally:
    cv2.destroyAllWindows()
