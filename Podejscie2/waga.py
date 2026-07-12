#!/usr/bin/env python3
"""
Estymacja wagi świń na żywo — OAK-D S2 (DepthAI v3).

Podejście: pomiary biometryczne z kamery głębi (bez ML).
Segmentacja z mapy głębi → wymiary (L, W, H) + objętość → waga.

Klawisze:
    C — kalibracja współczynnika (podaj znaną wagę w terminalu)
    +/- — ręczna korekta współczynnika ±5%
    T — zmiana progu min. wysokości ±1 cm
    D — tryb debug (pokaż mapę wysokości)
    Q — wyjście
"""
from __future__ import annotations

import json
import sys
import time
from collections import defaultdict, deque
from pathlib import Path

import cv2
import depthai as dai
import numpy as np

SCRIPT_DIR = Path(__file__).resolve().parent
CALIB_PATH = SCRIPT_DIR / "calibration.json"
COEFF_PATH = SCRIPT_DIR / "weight_coeff.json"

RGB_W, RGB_H = 1920, 1080

MIN_PIG_HEIGHT_CM = 5.0
MAX_PIG_HEIGHT_CM = 80.0
MIN_CONTOUR_AREA_PX = 3000
MAX_PIGS = 6

DEFAULT_COEFF = 0.0008

SMOOTH_N = 10
COLORS = [
    (0, 255, 0), (255, 100, 0), (0, 200, 255),
    (255, 0, 200), (100, 255, 100), (200, 200, 0),
]


def load_calibration() -> dict | None:
    if not CALIB_PATH.is_file():
        return None
    try:
        with open(CALIB_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return None


def load_coeff() -> float:
    if not COEFF_PATH.is_file():
        return DEFAULT_COEFF
    try:
        with open(COEFF_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
        return float(data.get("coeff", DEFAULT_COEFF))
    except (json.JSONDecodeError, OSError, ValueError):
        return DEFAULT_COEFF


def save_coeff(coeff: float) -> None:
    with open(COEFF_PATH, "w", encoding="utf-8") as f:
        json.dump({"coeff": round(coeff, 8), "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S")}, f, indent=2)


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


def segment_pigs(
    depth_frame: np.ndarray, camera_height_cm: float
) -> tuple[list[tuple[np.ndarray, np.ndarray]], np.ndarray]:
    depth_cm = depth_frame.astype(np.float64) / 10.0
    height_map = camera_height_cm - depth_cm
    height_map[depth_frame == 0] = 0.0

    pig_binary = (
        (height_map > MIN_PIG_HEIGHT_CM) & (height_map < MAX_PIG_HEIGHT_CM)
    ).astype(np.uint8) * 255

    kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (9, 9))
    pig_binary = cv2.morphologyEx(pig_binary, cv2.MORPH_CLOSE, kernel)
    pig_binary = cv2.morphologyEx(pig_binary, cv2.MORPH_OPEN, kernel)

    contours, _ = cv2.findContours(pig_binary, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    valid = [(c, cv2.contourArea(c)) for c in contours if cv2.contourArea(c) > MIN_CONTOUR_AREA_PX]
    valid.sort(key=lambda x: x[1], reverse=True)

    results: list[tuple[np.ndarray, np.ndarray]] = []
    for cnt, _ in valid[:MAX_PIGS]:
        mask = np.zeros(depth_frame.shape[:2], dtype=np.uint8)
        cv2.drawContours(mask, [cnt], -1, 255, -1)
        results.append((cnt, mask))

    return results, height_map


def measure_pig(
    contour: np.ndarray,
    mask: np.ndarray,
    height_map: np.ndarray,
    scale: float,
) -> dict | None:
    pixel_area = scale * scale

    area_px = float(cv2.contourArea(contour))
    area_cm2 = area_px * pixel_area

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

    heights = height_map[mask > 0]
    valid_h = heights[heights > 0]
    if len(valid_h) < 50:
        return None

    h_mean = float(np.mean(valid_h))
    h_max = float(np.max(valid_h))
    h_median = float(np.median(valid_h))
    h_std = float(np.std(valid_h))

    raw_volume = float(np.sum(valid_h) * pixel_area)

    axis_vec = eigenvectors[:, 0]
    half = length_px / 2.0
    p1 = (int(mean[0] - axis_vec[0] * half), int(mean[1] - axis_vec[1] * half))
    p2 = (int(mean[0] + axis_vec[0] * half), int(mean[1] + axis_vec[1] * half))
    center = (int(mean[0]), int(mean[1]))

    perp_vec = eigenvectors[:, 1]
    hw = width_px / 2.0
    w1 = (int(mean[0] - perp_vec[0] * hw), int(mean[1] - perp_vec[1] * hw))
    w2 = (int(mean[0] + perp_vec[0] * hw), int(mean[1] + perp_vec[1] * hw))

    return {
        "area_cm2": area_cm2,
        "length_cm": length_cm,
        "width_cm": width_cm,
        "h_mean": h_mean,
        "h_max": h_max,
        "h_median": h_median,
        "h_std": h_std,
        "raw_volume": raw_volume,
        "center": center,
        "axis_p1": p1,
        "axis_p2": p2,
        "width_p1": w1,
        "width_p2": w2,
        "contour": contour,
    }


def draw_pig_overlay(
    bgr: np.ndarray,
    m: dict,
    weight_kg: float,
    pig_idx: int,
    color: tuple[int, int, int],
) -> None:
    cv2.drawContours(bgr, [m["contour"]], -1, color, 2)
    cv2.line(bgr, m["axis_p1"], m["axis_p2"], (0, 0, 255), 2)
    cv2.line(bgr, m["width_p1"], m["width_p2"], (255, 0, 0), 2)

    cx, cy = m["center"]
    label = f"#{pig_idx + 1}  {weight_kg:.1f} kg"
    (tw, th), _ = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, 1.0, 3)
    cv2.rectangle(bgr, (cx - tw // 2 - 6, cy - th - 10), (cx + tw // 2 + 6, cy + 6), (0, 0, 0), -1)
    cv2.putText(bgr, label, (cx - tw // 2, cy), cv2.FONT_HERSHEY_SIMPLEX, 1.0, (0, 255, 255), 2, cv2.LINE_AA)

    info_x = m["axis_p2"][0] + 10
    info_y = m["axis_p2"][1]
    details = [
        f"L={m['length_cm']:.1f}cm",
        f"W={m['width_cm']:.1f}cm",
        f"H={m['h_mean']:.1f}cm (max {m['h_max']:.1f})",
        f"A={m['area_cm2']:.0f}cm2",
        f"V={m['raw_volume']:.0f}cm3",
    ]
    for i, txt in enumerate(details):
        y = info_y + i * 22
        cv2.putText(bgr, txt, (info_x, y), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (0, 0, 0), 3, cv2.LINE_AA)
        cv2.putText(bgr, txt, (info_x, y), cv2.FONT_HERSHEY_SIMPLEX, 0.55, color, 2, cv2.LINE_AA)


def draw_hud(
    bgr: np.ndarray,
    camera_height_cm: float,
    coeff: float,
    debug_mode: bool,
    n_pigs: int,
) -> None:
    h, w = bgr.shape[:2]
    lines = [
        f"Podloga: {camera_height_cm:.1f}cm | Coeff: {coeff:.6f} | Prog wys: {MIN_PIG_HEIGHT_CM:.0f}cm",
        f"Wykryto swin: {n_pigs}",
    ]
    if debug_mode:
        lines.append("[DEBUG] Mapa wysokosci aktywna")

    y0 = 28
    for i, txt in enumerate(lines):
        y = y0 + i * 24
        cv2.putText(bgr, txt, (12, y), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 0, 0), 3, cv2.LINE_AA)
        cv2.putText(bgr, txt, (12, y), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 0), 2, cv2.LINE_AA)

    help_lines = [
        "C=kalibruj  +/-=coeff  T/G=prog  D=debug  Q=wyjscie",
    ]
    for i, txt in enumerate(help_lines):
        y = h - 16 - i * 22
        cv2.putText(bgr, txt, (12, y), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (200, 200, 200), 1, cv2.LINE_AA)


def main() -> int:
    global MIN_PIG_HEIGHT_CM

    cal = load_calibration()
    if cal is None:
        print("BLAD: Brak calibration.json — uruchom najpierw kalibracja.py", file=sys.stderr)
        return 1

    camera_height_cm = float(cal["height_cm"])
    scale = float(cal["scale_cm_per_px"])
    coeff = load_coeff()

    print(f"Kalibracja: podloga={camera_height_cm:.1f}cm, skala={scale:.6f} cm/px")
    print(f"Wspolczynnik wagi: {coeff:.8f}")

    if camera_height_cm < 60:
        print(
            f"\n⚠ UWAGA: Wysokosc kamery ({camera_height_cm:.1f} cm) wydaje sie za niska.\n"
            f"  Upewnij sie, ze kalibracja mierzyla PODLOGE (bez swin w kadrze).\n"
            f"  Swinia 100kg ma grzbiet na ~55-65cm — kamera musi byc wyzej!\n"
        )

    pipeline, rgb_queue, depth_queue = build_pipeline()

    weight_history: dict[int, deque] = defaultdict(lambda: deque(maxlen=SMOOTH_N))
    debug_mode = False

    pipeline.start()
    try:
        with pipeline:
            win = "WagaSwin — estymacja wagi"
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
                depth_frame = depth_last.getFrame()

                pigs, height_map = segment_pigs(depth_frame, camera_height_cm)

                if debug_mode:
                    h_vis = np.clip(height_map, 0, camera_height_cm)
                    h_norm = (h_vis / max(camera_height_cm, 1) * 255).astype(np.uint8)
                    h_color = cv2.applyColorMap(h_norm, cv2.COLORMAP_JET)
                    bgr = cv2.addWeighted(bgr, 0.4, h_color, 0.6, 0)

                for i, (cnt, mask) in enumerate(pigs):
                    m = measure_pig(cnt, mask, height_map, scale)
                    if m is None:
                        continue

                    raw_kg = coeff * m["raw_volume"]
                    weight_history[i].append(raw_kg)
                    smooth_kg = float(np.median(list(weight_history[i])))

                    color = COLORS[i % len(COLORS)]
                    draw_pig_overlay(bgr, m, smooth_kg, i, color)

                draw_hud(bgr, camera_height_cm, coeff, debug_mode, len(pigs))

                show = cv2.resize(bgr, (1280, 720), interpolation=cv2.INTER_AREA)
                cv2.imshow(win, show)

                key = cv2.waitKey(1) & 0xFF
                if key == ord("q"):
                    break
                elif key == ord("d"):
                    debug_mode = not debug_mode
                elif key == ord("c"):
                    if pigs:
                        m = measure_pig(pigs[0][0], pigs[0][1], height_map, scale)
                        if m and m["raw_volume"] > 0:
                            try:
                                known = float(input("\nPodaj rzeczywista wage swini #1 [kg]: "))
                                if 5 < known < 500:
                                    coeff = known / m["raw_volume"]
                                    save_coeff(coeff)
                                    weight_history.clear()
                                    print(f"Nowy wspolczynnik: {coeff:.8f} (zapisano)")
                                else:
                                    print("Waga poza zakresem 5-500 kg")
                            except ValueError:
                                print("Nieprawidlowa wartosc")
                        else:
                            print("Brak pomiarow swini — nie mozna skalibrowaC")
                    else:
                        print("Brak wykrytej swini w kadrze")
                elif key == ord("+") or key == ord("="):
                    coeff *= 1.05
                    save_coeff(coeff)
                    weight_history.clear()
                    print(f"Coeff +5%: {coeff:.8f}")
                elif key == ord("-"):
                    coeff *= 0.95
                    save_coeff(coeff)
                    weight_history.clear()
                    print(f"Coeff -5%: {coeff:.8f}")
                elif key == ord("t"):
                    MIN_PIG_HEIGHT_CM = max(1.0, MIN_PIG_HEIGHT_CM + 1.0)
                    print(f"Prog min. wysokosci: {MIN_PIG_HEIGHT_CM:.0f} cm")
                elif key == ord("g"):
                    MIN_PIG_HEIGHT_CM = max(1.0, MIN_PIG_HEIGHT_CM - 1.0)
                    print(f"Prog min. wysokosci: {MIN_PIG_HEIGHT_CM:.0f} cm")
    finally:
        cv2.destroyAllWindows()

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
