"""UI na monitor 7\" 1024x600 ustawiony pionowo (= 600x1024).

Uklad:
  [ podglad kamery — gora ]
  [ panel danych jak dawny LCD — dol ]

Bez ILI9341 SPI — rysowanie OpenCV, live.py robi imshow fullscreen.
"""
from __future__ import annotations

import cv2
import numpy as np

# Natywny panel 1024x600 w pionie
SCREEN_W = 600
SCREEN_H = 1024

# Kolory BGR (OpenCV)
BG = (0, 0, 0)
WHITE = (255, 255, 255)
GREY = (150, 150, 150)
GREEN = (90, 220, 0)
YELLOW = (0, 210, 255)
CYAN = (255, 200, 0)
RED = (70, 70, 255)
PANEL_BG = (18, 18, 18)
HEADER_BG = (30, 60, 20)


def _fmt_height(height_cm: float | None) -> str:
    if height_cm is None:
        return "---"
    return f"{height_cm:.0f} cm"


def _put(
    img: np.ndarray,
    text: str,
    org: tuple[int, int],
    scale: float,
    color: tuple[int, int, int],
    thick: int = 2,
) -> None:
    cv2.putText(img, text, org, cv2.FONT_HERSHEY_SIMPLEX, scale, color, thick, cv2.LINE_AA)


def _centered(
    img: np.ndarray,
    text: str,
    y: int,
    scale: float,
    color: tuple[int, int, int],
    thick: int = 2,
) -> None:
    (tw, th), _ = cv2.getTextSize(text, cv2.FONT_HERSHEY_SIMPLEX, scale, thick)
    x = max(0, (img.shape[1] - tw) // 2)
    _put(img, text, (x, y), scale, color, thick)


def fit_camera_top(frame: np.ndarray, area_h: int) -> np.ndarray:
    """Skaluje klatke do szerokosci SCREEN_W, wstawia w pas o wysokosci area_h (czarne paski)."""
    canvas = np.zeros((area_h, SCREEN_W, 3), dtype=np.uint8)
    fh, fw = frame.shape[:2]
    if fw < 1 or fh < 1:
        return canvas
    scale = SCREEN_W / float(fw)
    new_w = SCREEN_W
    new_h = int(round(fh * scale))
    if new_h > area_h:
        scale = area_h / float(fh)
        new_h = area_h
        new_w = int(round(fw * scale))
    resized = cv2.resize(frame, (new_w, new_h), interpolation=cv2.INTER_AREA)
    x0 = (SCREEN_W - new_w) // 2
    y0 = (area_h - new_h) // 2
    canvas[y0 : y0 + new_h, x0 : x0 + new_w] = resized
    return canvas


def render_panel(
    state: str,
    *,
    height_cm: float | None = None,
    remaining_s: float = 0.0,
    samples: int = 0,
    measure_count: int = 0,
    result: dict | None = None,
    cal_height_cm: float | None = None,
    panel_h: int,
) -> np.ndarray:
    """Dolny panel — odpowiednik ekranow dawnego LCD."""
    img = np.full((panel_h, SCREEN_W, 3), PANEL_BG, dtype=np.uint8)
    mid = panel_h // 2

    if state == "idle":
        _centered(img, "WAGA SWIN", 48, 1.1, WHITE, 2)
        _centered(img, "Wysokosc", mid - 70, 0.8, GREY, 2)
        _centered(img, _fmt_height(height_cm), mid - 10, 2.2, CYAN, 3)
        _centered(img, "Nacisnij S / przycisk", mid + 70, 0.75, GREY, 2)
        _centered(img, "aby rozpoczac wazenie", mid + 110, 0.75, GREY, 2)

    elif state == "calibrating":
        _centered(img, "KALIBRACJA SKALI", 48, 1.0, CYAN, 2)
        _centered(img, f"{remaining_s:.1f} s", mid - 20, 2.4, WHITE, 3)
        _centered(img, f"probki: {samples}", mid + 60, 0.9, GREY, 2)

    elif state == "measuring":
        _centered(img, "WAZENIE...", 48, 1.1, GREEN, 2)
        _centered(img, f"{remaining_s:.1f} s", mid - 20, 2.4, WHITE, 3)
        _centered(img, f"pomiary: {measure_count}", mid + 60, 0.9, GREY, 2)

    elif state == "result":
        if result is None:
            _centered(img, "BRAK POMIAROW", mid - 40, 1.1, RED, 2)
            _centered(img, "nie wykryto swini", mid + 20, 0.8, GREY, 2)
            _centered(img, "Nacisnij S ponownie", mid + 70, 0.75, GREY, 2)
        else:
            cv2.rectangle(img, (0, 0), (SCREEN_W, 44), HEADER_BG, -1)
            _centered(img, "WYNIK WAZENIA", 32, 0.95, GREEN, 2)
            _centered(img, f"{result['mean']:.1f} kg", 110, 2.6, WHITE, 4)

            rows = [
                ("Mediana", f"{result['median']:.1f} kg", CYAN),
                ("Min", f"{result['min']:.1f} kg", YELLOW),
                ("Max", f"{result['max']:.1f} kg", YELLOW),
                ("Std", f"{result['std']:.1f} kg", GREY),
            ]
            if cal_height_cm is not None:
                rows.append(("Kalibr.", f"{cal_height_cm:.0f} cm", GREY))
            y = 160
            for label, value, color in rows:
                _put(img, label, (24, y), 0.75, GREY, 2)
                (vw, _), _ = cv2.getTextSize(value, cv2.FONT_HERSHEY_SIMPLEX, 0.75, 2)
                _put(img, value, (SCREEN_W - 24 - vw, y), 0.75, color, 2)
                y += 42
            _centered(img, f"{result['n']} pom. | S = ponownie", panel_h - 70, 0.7, GREY, 2)

    else:
        _centered(img, state.upper(), mid, 1.0, WHITE, 2)

    # Pasek wysokosci zawsze na dole panelu
    _centered(img, f"Wysokosc: {_fmt_height(height_cm)}", panel_h - 28, 0.7, CYAN, 2)
    return img


def compose_portrait(
    camera_frame: np.ndarray,
    state: str,
    *,
    height_cm: float | None = None,
    remaining_s: float = 0.0,
    samples: int = 0,
    measure_count: int = 0,
    result: dict | None = None,
    cal_height_cm: float | None = None,
    camera_ratio: float = 0.38,
) -> np.ndarray:
    """Pelny ekran 600x1024: kamera + panel LCD na dole."""
    cam_h = max(200, int(SCREEN_H * camera_ratio))
    panel_h = SCREEN_H - cam_h
    top = fit_camera_top(camera_frame, cam_h)
    panel = render_panel(
        state,
        height_cm=height_cm,
        remaining_s=remaining_s,
        samples=samples,
        measure_count=measure_count,
        result=result,
        cal_height_cm=cal_height_cm,
        panel_h=panel_h,
    )
    # cienka linia rozdzielajaca
    cv2.line(panel, (0, 0), (SCREEN_W, 0), (60, 60, 60), 2)
    return np.vstack([top, panel])
