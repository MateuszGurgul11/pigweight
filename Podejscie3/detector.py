"""
Detekcja i pomiar swini — Podejscie3.

Segmentacja: YOLOv8n-seg (models/pig_seg_best.pt)
Fallback:    Otsu threshold (jesli YOLO nic nie znajdzie)
Pomiary:     PCA na masce -> dlugosc, szerokosc, pole
Waga:        formula empiryczna (area / volume / combined)
Wygładzanie: mediana w oknie + filtr sigma (WeightSmoother)
"""
from __future__ import annotations

import os
from collections import deque
from pathlib import Path

import cv2
import numpy as np

# ── Stale ──────────────────────────────────────────────────────────────────
MODEL_PATH = Path(os.path.abspath(__file__)).parent / "models" / "pig_seg_best.pt"
MIN_CONTOUR_AREA_PX = 2000
YOLO_CONF = 0.25          # prog pewnosci detekcji

# ── Lazy-load modelu YOLO ──────────────────────────────────────────────────
_yolo_model = None

def _get_model():
    global _yolo_model
    if _yolo_model is None:
        from ultralytics import YOLO
        print(f"Ladowanie modelu YOLO: {MODEL_PATH}")
        _yolo_model = YOLO(str(MODEL_PATH))
    return _yolo_model


# ── Segmentacja YOLO ───────────────────────────────────────────────────────

def segment_pigs_yolo(image: np.ndarray) -> list[tuple[np.ndarray, np.ndarray]]:
    """
    Zwraca liste (contour, maska_binarna) dla kazdej swini wykrytej przez YOLO.
    Jesli brak detekcji — pusta lista.
    """
    model = _get_model()
    h, w = image.shape[:2]
    results = model(image, verbose=False, conf=YOLO_CONF)[0]

    pigs: list[tuple[np.ndarray, np.ndarray]] = []
    if results.masks is None:
        return pigs

    for mask_tensor in results.masks.data:
        # maska float32 [0..1] w rozmiarze wyjsciowym modelu
        mask_f = mask_tensor.cpu().numpy()
        mask_u8 = (mask_f * 255).astype(np.uint8)
        mask_u8 = cv2.resize(mask_u8, (w, h), interpolation=cv2.INTER_LINEAR)
        _, mask_bin = cv2.threshold(mask_u8, 127, 255, cv2.THRESH_BINARY)

        contours, _ = cv2.findContours(mask_bin, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        if not contours:
            continue
        cnt = max(contours, key=cv2.contourArea)
        if cv2.contourArea(cnt) < MIN_CONTOUR_AREA_PX:
            continue
        pigs.append((cnt, mask_bin))

    return pigs


# ── Fallback Otsu ──────────────────────────────────────────────────────────

def segment_pigs_otsu(image: np.ndarray) -> list[tuple[np.ndarray, np.ndarray]]:
    """Prosta segmentacja Otsu — zwraca liste (contour, maska) dla kazdego jasnego obiektu."""
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    blurred = cv2.GaussianBlur(gray, (11, 11), 0)
    _, binary = cv2.threshold(blurred, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (15, 15))
    binary = cv2.morphologyEx(binary, cv2.MORPH_CLOSE, kernel)
    binary = cv2.morphologyEx(binary, cv2.MORPH_OPEN, kernel)
    contours, _ = cv2.findContours(binary, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    valid = [(c, binary) for c in contours if cv2.contourArea(c) > MIN_CONTOUR_AREA_PX]
    if not valid:
        return []
    # Tylko najwkiszy kontur (pojedyncza swinia)
    best = max(valid, key=lambda x: cv2.contourArea(x[0]))
    return [best]


# ── Pomiary PCA ────────────────────────────────────────────────────────────

def measure_pig(contour: np.ndarray, mask: np.ndarray, scale: float) -> dict | None:
    """Oblicza dlugosc/szerokosc/pole metodą PCA na pikselach maski."""
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
    width_px  = 4.0 * np.sqrt(max(0.0, eigenvalues[1]))
    length_cm = length_px * scale
    width_cm  = width_px  * scale

    axis_vec = eigenvectors[:, 0]
    half = length_px / 2.0
    p1 = (int(mean[0] - axis_vec[0] * half), int(mean[1] - axis_vec[1] * half))
    p2 = (int(mean[0] + axis_vec[0] * half), int(mean[1] + axis_vec[1] * half))
    perp = eigenvectors[:, 1]
    hw = width_px / 2.0
    w1 = (int(mean[0] - perp[0] * hw), int(mean[1] - perp[1] * hw))
    w2 = (int(mean[0] + perp[0] * hw), int(mean[1] + perp[1] * hw))

    return {
        "area_cm2":  round(area_cm2, 1),
        "length_cm": round(length_cm, 1),
        "width_cm":  round(width_cm, 1),
        "center":    (int(mean[0]), int(mean[1])),
        "axis_p1": p1, "axis_p2": p2,
        "width_p1": w1, "width_p2": w2,
        "contour": contour,
    }


# ── Glowna funkcja detekcji ────────────────────────────────────────────────

def detect_pigs(image: np.ndarray, scale: float) -> tuple[list[dict], str]:
    """
    Wykrywa wszystkie swinie na obrazie.
    Zwraca (lista_pomiarow, zrodlo) gdzie zrodlo = 'yolo' lub 'otsu'.
    Kazdy pomiar to dict z area_cm2, length_cm, width_cm, center, contour itp.
    """
    pigs_raw = segment_pigs_yolo(image)
    source = "yolo"

    if not pigs_raw:
        pigs_raw = segment_pigs_otsu(image)
        source = "otsu"

    measurements = []
    for cnt, mask in pigs_raw:
        m = measure_pig(cnt, mask, scale)
        if m is not None:
            measurements.append(m)

    return measurements, source


def detect_best_pig(image: np.ndarray, scale: float) -> tuple[dict | None, list[dict], str]:
    """
    Zwraca (najlepsza_swinia, wszystkie_pomiary, info).
    Najlepsza = najblizej srodka kadru.
    Kompatybilna z interfejsem Podejscie2.
    """
    h, w = image.shape[:2]
    cx_img, cy_img = w // 2, h // 2

    measurements, source = detect_pigs(image, scale)

    if not measurements:
        return None, [], f"brak detekcji ({source})"

    def dist_to_center(m: dict) -> float:
        cx, cy = m["center"]
        return float((cx - cx_img) ** 2 + (cy - cy_img) ** 2)

    best = min(measurements, key=dist_to_center)
    return best, measurements, source


# ── Estymacja wagi ─────────────────────────────────────────────────────────

def estimate_weight(m: dict, coeffs: dict) -> float:
    area   = m["area_cm2"]
    length = m["length_cm"]
    width  = m["width_cm"]
    w_area   = coeffs.get("coeff_area",   0.033)  * area
    w_volume = coeffs.get("coeff_volume", 0.0008) * length * width * width
    method = coeffs.get("method", "area")
    if method == "volume":
        return max(0.0, w_volume)
    if method == "combined":
        return max(0.0, (w_area + w_volume) / 2.0)
    return max(0.0, w_area)


# ── Wygładzanie wagi ───────────────────────────────────────────────────────

class WeightSmoother:
    """Mediana w oknie + odrzucanie outlierow (|x - median| > sigma * std)."""

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

    def clear(self) -> None:
        self.history.clear()
