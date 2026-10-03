"""Test UI: kamera 90° + pasek wysokosc/waga (600x1024).

    python check/hello_screen.py
"""
import sys
import time

import cv2
import numpy as np

from display import SCREEN_H, SCREEN_W, compose_portrait

WINDOW = "PigWeight monitor test"


def fake_camera(t: float) -> np.ndarray:
    img = np.zeros((720, 1280, 3), dtype=np.uint8)
    img[:] = (50, 50, 50)
    cv2.rectangle(img, (200, 150), (1080, 570), (80, 140, 80), -1)
    cv2.putText(img, "KAMERA", (480, 380), cv2.FONT_HERSHEY_SIMPLEX, 2.0, (220, 220, 220), 3)
    return img


cv2.namedWindow(WINDOW, cv2.WINDOW_NORMAL)
cv2.resizeWindow(WINDOW, SCREEN_W, SCREEN_H)
cv2.setWindowProperty(WINDOW, cv2.WND_PROP_FULLSCREEN, cv2.WINDOW_FULLSCREEN)

print(f"Test {SCREEN_W}x{SCREEN_H}. Q / Esc = koniec.")
t0 = time.monotonic()
while True:
    t = time.monotonic() - t0
    phase = int(t // 3) % 3
    if phase == 0:
        state, kg, rem = "idle", None, 0.0
    elif phase == 1:
        state, kg, rem = "measuring", 98.0 + (t % 3) * 2, 3.0 - (t % 3)
    else:
        state, kg, rem = "result", 112.4, 0.0
    screen = compose_portrait(
        fake_camera(t),
        state,
        height_cm=131.0,
        weight_kg=kg,
        remaining_s=rem,
    )
    cv2.imshow(WINDOW, screen)
    if cv2.waitKey(30) & 0xFF in (ord("q"), 27):
        break

cv2.destroyAllWindows()
sys.exit(0)
