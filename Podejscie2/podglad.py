#!/usr/bin/env python3
"""
Podgląd na żywo: OAK-D S2 (DepthAI v3).
Wyświetla odległość kamery od podłogi (z kalibracji) oraz głębię w środku kadru
i szacowaną wysokość obiektu nad podłogą (przy pionowej kamerze: H_kal − Z).
"""
from __future__ import annotations

import json
import sys
from collections import deque
from pathlib import Path

import cv2
import depthai as dai
import numpy as np

SCRIPT_DIR = Path(__file__).resolve().parent
CALIB_PATH = SCRIPT_DIR / "calibration.json"

RGB_W, RGB_H = 1920, 1080
ROI_HALF = 20  # środkowy ROI (2*ROI_HALF)² — jak w kalibracji
SMOOTH_N = 7


def load_calibration() -> dict | None:
    if not CALIB_PATH.is_file():
        return None
    try:
        with open(CALIB_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return None


def median_depth_mm(frame: np.ndarray, half: int) -> float | None:
    h, w = frame.shape[:2]
    cy, cx = h // 2, w // 2
    roi = frame[cy - half : cy + half, cx - half : cx + half]
    valid = roi[roi > 0]
    if valid.size == 0:
        return None
    return float(np.median(valid))


def build_pipeline() -> tuple[dai.Pipeline, dai.MessageQueue, dai.MessageQueue]:
    pipeline = dai.Pipeline()

    cam_rgb = pipeline.create(dai.node.Camera)
    cam_rgb.build(dai.CameraBoardSocket.CAM_A)
    rgb_out = cam_rgb.requestOutput((RGB_W, RGB_H), type=dai.ImgFrame.Type.BGR888p)
    rgb_queue = rgb_out.createOutputQueue(maxSize=2, blocking=False)

    stereo = pipeline.create(dai.node.StereoDepth)
    stereo.build(autoCreateCameras=True, presetMode=dai.node.StereoDepth.PresetMode.ACCURACY)
    stereo.setDepthAlign(dai.CameraBoardSocket.CAM_A)
    stereo.setOutputSize(RGB_W, RGB_H)
    depth_queue = stereo.depth.createOutputQueue(maxSize=2, blocking=False)

    return pipeline, rgb_queue, depth_queue


def draw_overlay(
    bgr: np.ndarray,
    height_floor_cm: float | None,
    z_center_cm: float | None,
    obj_above_floor_cm: float | None,
) -> None:
    h, w = bgr.shape[:2]
    cx, cy = w // 2, h // 2
    cv2.drawMarker(bgr, (cx, cy), (0, 255, 255), markerType=cv2.MARKER_CROSS, markerSize=28, thickness=2)
    cv2.rectangle(
        bgr,
        (cx - ROI_HALF, cy - ROI_HALF),
        (cx + ROI_HALF, cy + ROI_HALF),
        (0, 255, 255),
        1,
    )

    lines: list[str] = []
    if height_floor_cm is not None:
        lines.append(f"Kamera — podloga (kalibr.): {height_floor_cm:.1f} cm")
    else:
        lines.append("Brak calibration.json — tylko glebia w srodku")

    if z_center_cm is not None:
        lines.append(f"Srodek kadru (do powierzchni): {z_center_cm:.1f} cm")
    else:
        lines.append("Srodek kadru: brak odczytu glebi")

    if obj_above_floor_cm is not None:
        lines.append(f"Szac. obiekt nad podloga: {obj_above_floor_cm:.1f} cm")
    elif height_floor_cm is not None and z_center_cm is not None:
        lines.append("Szac. obiekt nad podloga: —")

    y0 = 28
    for i, text in enumerate(lines):
        y = y0 + i * 26
        cv2.putText(bgr, text, (12, y), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 0, 0), 3, cv2.LINE_AA)
        cv2.putText(bgr, text, (12, y), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 0), 2, cv2.LINE_AA)

    cv2.putText(
        bgr,
        "Q — wyjscie",
        (12, h - 16),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.55,
        (220, 220, 220),
        1,
        cv2.LINE_AA,
    )


def main() -> int:
    cal = load_calibration()
    height_cm = float(cal["height_cm"]) if cal else None

    if cal is None:
        print(f"Uwaga: nie znaleziono {CALIB_PATH.name} — uruchom najpierw kalibracja.py.", file=sys.stderr)

    pipeline, rgb_queue, depth_queue = build_pipeline()

    z_hist: deque[float] = deque(maxlen=SMOOTH_N)

    pipeline.start()
    try:
        with pipeline:
            win = "OAK-D S2 — podglad glebi"
            cv2.namedWindow(win, cv2.WINDOW_NORMAL)
            cv2.resizeWindow(win, 1280, 720)

            while pipeline.isRunning():
                rgb_last = None
                depth_last = None
                while True:
                    r = rgb_queue.tryGet()
                    d = depth_queue.tryGet()
                    if r is not None:
                        rgb_last = r
                    if d is not None:
                        depth_last = d
                    if r is None and d is None:
                        break

                if rgb_last is None or depth_last is None:
                    continue

                bgr = rgb_last.getCvFrame()
                depth_mm = depth_last.getFrame()

                z_mm = median_depth_mm(depth_mm, ROI_HALF)
                if z_mm is not None:
                    z_hist.append(z_mm / 10.0)
                z_smooth = float(np.median(z_hist)) if z_hist else None

                obj_above: float | None = None
                if height_cm is not None and z_smooth is not None:
                    # Kamera w dol: blizsza powierzchnia => mniejsze Z niz pusta podloga
                    obj_above = max(0.0, height_cm - z_smooth)

                draw_overlay(bgr, height_cm, z_smooth, obj_above)

                show = cv2.resize(bgr, (1280, 720), interpolation=cv2.INTER_AREA)
                cv2.imshow(win, show)
                if cv2.waitKey(1) & 0xFF == ord("q"):
                    break
    finally:
        cv2.destroyAllWindows()

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
