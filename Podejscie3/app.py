#!/usr/bin/env python3
"""
Web interface — estymacja wagi swini ze zdjecia — Podejscie3 (YOLO-seg).

Uruchomienie:
    cd Podejscie3
    ..\Podejscie2\venv\Scripts\python -m uvicorn app:app --reload --port 8001
"""
from __future__ import annotations

import base64
import json
import time
from pathlib import Path

import cv2
import numpy as np
from fastapi import FastAPI, File, Form, UploadFile
from fastapi.responses import HTMLResponse

from detector import detect_best_pig, detect_pigs, estimate_weight, measure_pig

SCRIPT_DIR = Path(__file__).resolve().parent
CALIB_PATH = SCRIPT_DIR / "calibration.json"
COEFF_PATH = SCRIPT_DIR / "weight_coeff.json"
HTML_PATH = SCRIPT_DIR / "index.html"


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


def save_coeff(data: dict) -> None:
    existing = load_coeff()
    existing.update(data)
    existing["timestamp"] = time.strftime("%Y-%m-%dT%H:%M:%S")
    with open(COEFF_PATH, "w", encoding="utf-8") as f:
        json.dump(existing, f, indent=2)


def draw_result(image: np.ndarray, pigs: list[dict], best: dict | None, weights: list[float]) -> np.ndarray:
    out = image.copy()

    for i, m in enumerate(pigs):
        is_best = (m is best)
        color = (0, 255, 0) if is_best else (0, 200, 255)
        thickness = 3 if is_best else 1
        cv2.drawContours(out, [m["contour"]], -1, color, thickness)

        if is_best and weights:
            weight = weights[0]
            cv2.line(out, m["axis_p1"], m["axis_p2"], (0, 0, 255), 3)
            cv2.line(out, m["width_p1"], m["width_p2"], (255, 0, 0), 3)

            cx, cy = m["center"]
            label = f"{weight:.1f} kg"
            (tw, th), _ = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, 1.5, 4)
            cv2.rectangle(out, (cx - tw//2 - 10, cy - th - 16), (cx + tw//2 + 10, cy + 12), (0, 0, 0), -1)
            cv2.putText(out, label, (cx - tw//2, cy), cv2.FONT_HERSHEY_SIMPLEX, 1.5, (0, 255, 255), 4, cv2.LINE_AA)

            info_x, info_y = m["axis_p2"][0] + 15, m["axis_p2"][1]
            for j, txt in enumerate([f"L={m['length_cm']}cm", f"W={m['width_cm']}cm", f"A={m['area_cm2']}cm2"]):
                y = info_y + j * 28
                cv2.putText(out, txt, (info_x, y), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 0, 0), 4, cv2.LINE_AA)
                cv2.putText(out, txt, (info_x, y), cv2.FONT_HERSHEY_SIMPLEX, 0.7, color, 2, cv2.LINE_AA)

    return out


app = FastAPI(title="WagaSwin-P3")


@app.get("/", response_class=HTMLResponse)
def index():
    return HTML_PATH.read_text(encoding="utf-8")


@app.post("/analyze")
async def analyze(image: UploadFile = File(...)):
    blob = await image.read()
    arr = np.frombuffer(blob, dtype=np.uint8)
    img = cv2.imdecode(arr, cv2.IMREAD_COLOR)
    if img is None:
        return {"error": "Nie udalo sie zdekodowac obrazu"}

    cal = load_calibration()
    scale = float(cal["scale_cm_per_px"])
    coeffs = load_coeff()

    best, all_pigs, source = detect_best_pig(img, scale)

    weights = []
    result = None
    if best is not None:
        best["contour_pts"] = best["contour"].squeeze().tolist()
        weight = round(estimate_weight(best, coeffs), 1)
        weights.append(weight)
        result = {
            "weight_kg": weight,
            "length_cm": best["length_cm"],
            "width_cm": best["width_cm"],
            "area_cm2": best["area_cm2"],
            "pig_count": len(all_pigs),
            "source": source,
        }

    annotated = draw_result(img, all_pigs, best, weights)
    _, buf = cv2.imencode(".jpg", annotated, [cv2.IMWRITE_JPEG_QUALITY, 90])
    b64 = base64.b64encode(buf.tobytes()).decode("ascii")

    return {
        "image": b64,
        "pig": result,
        "source": source,
        "pig_count": len(all_pigs),
        "calibration": {
            "height_cm": cal["height_cm"],
            "scale_cm_per_px": cal["scale_cm_per_px"],
            "fov": f"{cal['fov_width_cm']:.0f} x {cal['fov_height_cm']:.0f} cm",
        },
        "coeffs": {k: v for k, v in coeffs.items() if k != "timestamp"},
    }


@app.post("/calibrate_weight")
async def calibrate_weight(
    image: UploadFile = File(...),
    known_weight: float = Form(...),
    pig_index: int = Form(0),
):
    blob = await image.read()
    arr = np.frombuffer(blob, dtype=np.uint8)
    img = cv2.imdecode(arr, cv2.IMREAD_COLOR)
    if img is None:
        return {"error": "Nie udalo sie zdekodowac obrazu"}

    cal = load_calibration()
    scale = float(cal["scale_cm_per_px"])

    best, _, source = detect_best_pig(img, scale)
    if best is None:
        return {"error": f"Nie wykryto swini ({source})"}

    area = best["area_cm2"]
    length = best["length_cm"]
    width = best["width_cm"]

    new_coeff_area = known_weight / area if area > 0 else 0.033
    new_coeff_volume = known_weight / (length * width * width) if (length * width) > 0 else 0.0008

    save_coeff({
        "coeff_area": round(new_coeff_area, 8),
        "coeff_volume": round(new_coeff_volume, 8),
    })

    return {
        "coeff_area": round(new_coeff_area, 8),
        "coeff_volume": round(new_coeff_volume, 8),
        "measurements": {"area_cm2": area, "length_cm": length, "width_cm": width},
        "known_weight": known_weight,
        "source": source,
    }


@app.post("/set_method")
async def set_method(method: str = Form("area")):
    if method not in ("area", "volume", "combined"):
        return {"error": "Metoda musi byc: area, volume, combined"}
    save_coeff({"method": method})
    return {"method": method}
