"""UI na monitor 7\" 1024x600 ustawiony pionowo (= 600x1024).

Uklad:
  [ podglad kamery obrocony 90° — wiekszosc ekranu ]
  [ waski pasek: wysokosc + waga ]

Bez ILI9341 SPI — rysowanie OpenCV.
"""
from __future__ import annotations

import cv2
import numpy as np

# Natywny panel 1024x600 w pionie
SCREEN_W = 600
SCREEN_H = 1024

# Waski pasek statusu na dole
BAR_H = 110
CAM_H = SCREEN_H - BAR_H

# Kolory BGR
BG = (0, 0, 0)
BAR_BG = (22, 22, 22)
WHITE = (255, 255, 255)
GREY = (160, 160, 160)
CYAN = (255, 200, 0)
YELLOW = (0, 255, 255)
GREEN = (90, 220, 0)
RED = (70, 70, 255)


def _fmt_height(height_cm: float | None) -> str:
    if height_cm is None:
        return "---"
    return f"{height_cm:.0f} cm"


def _fmt_weight(kg: float | None) -> str:
    if kg is None:
        return "---"
    return f"{kg:.1f} kg"


def _put(
    img: np.ndarray,
    text: str,
    org: tuple[int, int],
    scale: float,
    color: tuple[int, int, int],
    thick: int = 2,
) -> None:
    cv2.putText(img, text, org, cv2.FONT_HERSHEY_SIMPLEX, scale, color, thick, cv2.LINE_AA)


def rotate_camera_90(frame: np.ndarray) -> np.ndarray:
    """Obrot podgladu o 90° w prawo (dostosowanie do pionowego monitora)."""
    return cv2.rotate(frame, cv2.ROTATE_90_CLOCKWISE)


def fit_camera(frame: np.ndarray) -> np.ndarray:
    """Kamera (po obrocie) — caly kadr widoczny (contain), bez ucinania gory/dolu."""
    canvas = np.zeros((CAM_H, SCREEN_W, 3), dtype=np.uint8)
    fh, fw = frame.shape[:2]
    if fw < 1 or fh < 1:
        return canvas

    # contain: miesci sie caly obraz, ewentualnie czarne paski po bokach
    scale = min(SCREEN_W / float(fw), CAM_H / float(fh))
    new_w = max(1, int(round(fw * scale)))
    new_h = max(1, int(round(fh * scale)))
    resized = cv2.resize(frame, (new_w, new_h), interpolation=cv2.INTER_AREA)

    x0 = (SCREEN_W - new_w) // 2
    y0 = (CAM_H - new_h) // 2  # wycentrowane w pionie; nic nie ucinamy
    canvas[y0 : y0 + new_h, x0 : x0 + new_w] = resized
    return canvas


def render_bar(
    *,
    height_cm: float | None = None,
    weight_kg: float | None = None,
    state: str = "idle",
    remaining_s: float = 0.0,
) -> np.ndarray:
    """Maly pasek: wysokosc + waga (+ krotki status fazy)."""
    img = np.full((BAR_H, SCREEN_W, 3), BAR_BG, dtype=np.uint8)
    cv2.line(img, (0, 0), (SCREEN_W, 0), (70, 70, 70), 2)

    # Lewa: wysokosc
    _put(img, "WYS.", (16, 38), 0.55, GREY, 1)
    _put(img, _fmt_height(height_cm), (16, 82), 1.15, CYAN, 2)

    # Srodek / prawa: waga
    wtxt = _fmt_weight(weight_kg)
    (tw, _), _ = cv2.getTextSize(wtxt, cv2.FONT_HERSHEY_SIMPLEX, 1.5, 3)
    _put(img, "WAGA", (SCREEN_W - tw - 16, 38), 0.55, GREY, 1)
    _put(img, wtxt, (SCREEN_W - tw - 16, 82), 1.5, YELLOW, 3)

    # Krotki status fazy na srodku (bez instrukcji klikania)
    if state == "calibrating":
        _put(img, f"kalibr. {remaining_s:.0f}s", (SCREEN_W // 2 - 70, 38), 0.55, CYAN, 1)
    elif state == "measuring":
        _put(img, f"pomiar {remaining_s:.0f}s", (SCREEN_W // 2 - 70, 38), 0.55, GREEN, 1)
    elif state == "result" and weight_kg is None:
        _put(img, "brak pomiaru", (SCREEN_W // 2 - 70, 38), 0.55, RED, 1)

    return img


def compose_portrait(
    camera_frame: np.ndarray,
    state: str,
    *,
    height_cm: float | None = None,
    weight_kg: float | None = None,
    remaining_s: float = 0.0,
    samples: int = 0,  # zachowane dla kompatybilnosci wywolania
    measure_count: int = 0,
    result: dict | None = None,
    cal_height_cm: float | None = None,
    camera_ratio: float = 0.0,  # nieuzywane — kamera zawsze CAM_H
) -> np.ndarray:
    """Pelny ekran 600x1024: kamera 90° + pasek wysokosc/waga."""
    _ = samples, measure_count, cal_height_cm, camera_ratio

    # Waga do paska: wynik sesji albo biezacy odczyt
    kg = weight_kg
    if kg is None and result is not None:
        kg = float(result.get("mean", result.get("median", 0.0)))

    rotated = rotate_camera_90(camera_frame)
    top = fit_camera(rotated)
    bar = render_bar(
        height_cm=height_cm,
        weight_kg=kg,
        state=state,
        remaining_s=remaining_s,
    )
    return np.vstack([top, bar])
