#!/usr/bin/env python3
"""
Web interface — estymacja wagi swini ze zdjecia (widok z gory).

Segmentacja kolorem (jasna swinia na ciemnej podlodze) + pomiary 2D
z kalibracji kamery → waga z formuly empirycznej.

Uruchomienie:
    cd Podejscie2
    venv\\Scripts\\python -m uvicorn app:app --reload --port 8000
"""
from __future__ import annotations

import base64
import io
import json
import time
from pathlib import Path

import cv2
import numpy as np
from fastapi import FastAPI, File, Form, UploadFile
from fastapi.responses import HTMLResponse

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


def segment_pig(image: np.ndarray) -> tuple[np.ndarray | None, np.ndarray]:
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


def draw_result(image: np.ndarray, m: dict | None, weight: float) -> np.ndarray:
    out = image.copy()
    if m is None:
        return out

    color = (0, 255, 0)
    cv2.line(out, m["axis_p1"], m["axis_p2"], (0, 0, 255), 3)
    cv2.line(out, m["width_p1"], m["width_p2"], (255, 0, 0), 3)

    pts = np.array([m.get("contour_pts", [])], dtype=np.int32)
    if pts.size > 0:
        cv2.drawContours(out, [pts.reshape(-1, 1, 2)], -1, color, 2)

    cx, cy = m["center"]
    label = f"{weight:.1f} kg"
    (tw, th), _ = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, 1.5, 4)
    cv2.rectangle(out, (cx - tw//2 - 10, cy - th - 16), (cx + tw//2 + 10, cy + 12), (0, 0, 0), -1)
    cv2.putText(out, label, (cx - tw//2, cy), cv2.FONT_HERSHEY_SIMPLEX, 1.5, (0, 255, 255), 4, cv2.LINE_AA)

    info_x, info_y = m["axis_p2"][0] + 15, m["axis_p2"][1]
    for j, txt in enumerate([
        f"L={m['length_cm']}cm", f"W={m['width_cm']}cm", f"A={m['area_cm2']}cm2"
    ]):
        y = info_y + j * 28
        cv2.putText(out, txt, (info_x, y), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 0, 0), 4, cv2.LINE_AA)
        cv2.putText(out, txt, (info_x, y), cv2.FONT_HERSHEY_SIMPLEX, 0.7, color, 2, cv2.LINE_AA)

    return out


app = FastAPI(title="WagaSwin")


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

    contour, binary = segment_pig(img)

    pig = None
    weight = 0.0
    if contour is not None:
        m = measure_pig(contour, binary, scale)
        if m is not None:
            pig = m
            pig["contour_pts"] = pig["contour"].squeeze().tolist()
            weight = round(estimate_weight(pig, coeffs), 1)

    annotated = draw_result(img, pig, weight)
    _, buf = cv2.imencode(".jpg", annotated, [cv2.IMWRITE_JPEG_QUALITY, 90])
    b64 = base64.b64encode(buf.tobytes()).decode("ascii")

    result = None
    if pig is not None:
        result = {
            "weight_kg": weight,
            "length_cm": pig["length_cm"],
            "width_cm": pig["width_cm"],
            "area_cm2": pig["area_cm2"],
        }

    return {
        "image": b64,
        "pig": result,
        "calibration": {
            "height_cm": cal["height_cm"],
            "scale_cm_per_px": cal["scale_cm_per_px"],
            "px_per_cm": cal["px_per_cm"],
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

    contour, binary = segment_pig(img)
    if contour is None:
        return {"error": "Nie wykryto swini"}
    m = measure_pig(contour, binary, scale)
    if m is None:
        return {"error": "Nie mozna zmierzyc swini"}

    area = m["area_cm2"]
    length = m["length_cm"]
    width = m["width_cm"]

    new_coeff_area = known_weight / area if area > 0 else 0.033
    new_coeff_volume = known_weight / (length * width * width) if (length * width) > 0 else 0.0008

    save_coeff({
        "coeff_area": round(new_coeff_area, 8),
        "coeff_volume": round(new_coeff_volume, 8),
    })

    return {
        "coeff_area": round(new_coeff_area, 8),
        "coeff_volume": round(new_coeff_volume, 8),
        "measurements": {
            "area_cm2": m["area_cm2"],
            "length_cm": m["length_cm"],
            "width_cm": m["width_cm"],
        },
        "known_weight": known_weight,
    }


@app.post("/set_method")
async def set_method(method: str = Form("area")):
    if method not in ("area", "volume", "combined"):
        return {"error": "Metoda musi byc: area, volume, combined"}
    save_coeff({"method": method})
    return {"method": method}
