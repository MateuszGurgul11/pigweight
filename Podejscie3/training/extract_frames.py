"""
Ekstrakcja klatek z wszystkich filmow datasetu do folderu datasets/.
Zapisuje co N-ta klatke (domyslnie co 15) jako JPEG.
"""
import os
import sys
from pathlib import Path

import cv2
import numpy as np

STEP = 15       # co ile klatek zapisujemy (przy 15fps -> 1 klatka/sek)
QUALITY = 95

SCRIPT_DIR = Path(os.path.abspath(__file__)).parent
DATASET_ROOT = SCRIPT_DIR.parent / "Podejscie1" / "dataset"
OUTPUT_DIR = SCRIPT_DIR / "datasets"

videos = sorted(
    p for p in DATASET_ROOT.glob("pig_*/rgb_video.mp4")
    if "__MACOSX" not in p.parts
)

if not videos:
    print("BLAD: Brak filmow w", DATASET_ROOT)
    sys.exit(1)

OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
total_saved = 0

encode_params = [cv2.IMWRITE_JPEG_QUALITY, QUALITY]


def save_jpg(path: Path, frame: np.ndarray) -> bool:
    """cv2.imwrite nie obsluguje Unicode na Windows — uzywamy imencode + open()."""
    ok, buf = cv2.imencode(".jpg", frame, encode_params)
    if not ok:
        return False
    path.write_bytes(buf.tobytes())
    return True


for video_path in videos:
    pig_name = video_path.parent.name
    out_dir = OUTPUT_DIR / pig_name
    out_dir.mkdir(exist_ok=True)

    cap = cv2.VideoCapture(str(video_path))
    if not cap.isOpened():
        print("  POMINIETY:", pig_name)
        continue

    total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    fps = cap.get(cv2.CAP_PROP_FPS)
    saved = 0
    idx = 0

    while True:
        ret, frame = cap.read()
        if not ret:
            break
        if idx % STEP == 0:
            fname = out_dir / f"{pig_name}_f{idx:05d}.jpg"
            if save_jpg(fname, frame):
                saved += 1
        idx += 1

    cap.release()
    print(f"  {pig_name}: {total} klatek ({fps:.0f}fps) -> zapisano {saved} JPG")
    total_saved += saved

print()
print("Gotowe! Lacznie zapisano", total_saved, "klatek do:", OUTPUT_DIR)
