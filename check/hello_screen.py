"""Test layoutu monitora 7\" 1024x600 w pionie (600x1024).

    python check/hello_screen.py

Q / Esc = koniec.
"""
import sys
import time

import cv2
import numpy as np

from display import SCREEN_H, SCREEN_W, compose_portrait

WINDOW = "PigWeight monitor test"


def fake_camera(t: float) -> np.ndarray:
    img = np.zeros((720, 1280, 3), dtype=np.uint8)
    img[:] = (40, 40, 40)
    cv2.putText(img, "KAMERA", (480, 360), cv2.FONT_HERSHEY_SIMPLEX, 2.0, (0, 220, 90), 3)
    cv2.putText(img, f"t={t:.1f}s", (520, 420), cv2.FONT_HERSHEY_SIMPLEX, 1.0, (200, 200, 200), 2)
    return img


cv2.namedWindow(WINDOW, cv2.WINDOW_NORMAL)
cv2.resizeWindow(WINDOW, SCREEN_W, SCREEN_H)
cv2.setWindowProperty(WINDOW, cv2.WND_PROP_FULLSCREEN, cv2.WINDOW_FULLSCREEN)

states = [
    ("idle", {}),
    ("calibrating", {"remaining_s": 0.8, "samples": 12}),
    ("measuring", {"remaining_s": 2.1, "measure_count": 40}),
    (
        "result",
        {
            "result": {
                "n": 48,
                "mean": 112.4,
                "median": 111.8,
                "min": 98.2,
                "max": 130.5,
                "std": 6.3,
            },
            "cal_height_cm": 131.0,
        },
    ),
]

print(f"Test UI {SCREEN_W}x{SCREEN_H}. Q / Esc = koniec.")
idx = 0
t0 = time.monotonic()
while True:
    t = time.monotonic() - t0
    idx = int(t // 2.5) % len(states)
    state, kwargs = states[idx]
    screen = compose_portrait(
        fake_camera(t),
        state,
        height_cm=131.0,
        **kwargs,
    )
    cv2.imshow(WINDOW, screen)
    key = cv2.waitKey(30) & 0xFF
    if key in (ord("q"), 27):
        break

cv2.destroyAllWindows()
sys.exit(0)
