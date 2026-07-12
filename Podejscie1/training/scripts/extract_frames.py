#!/usr/bin/env python3
"""
Wycina klatki z nagrań pionowych (widok z góry) do folderu z obrazami pod etykietowanie YOLO.

Przykład:
  pip install opencv-python-headless
  python scripts/extract_frames.py --input ../../video --output ../datasets/pig_top/images/train --every 15

Domyślnie: input = repo/video, output = datasets/pig_top/images/train (względem katalogu training/).
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

try:
    import cv2
except ImportError:
    print("Zainstaluj: pip install opencv-python-headless", file=sys.stderr)
    raise SystemExit(1) from None

VIDEO_EXT = {".mp4", ".mov", ".mkv", ".avi", ".webm", ".m4v"}


def main() -> None:
    training_dir = Path(__file__).resolve().parent.parent
    repo_root = training_dir.parent
    default_in = repo_root / "video"
    default_out = training_dir / "datasets" / "pig_top" / "images" / "train"

    p = argparse.ArgumentParser(description="Ekstrakcja klatek z wideo do zbioru treningowego")
    p.add_argument(
        "--input",
        type=Path,
        default=default_in,
        help=f"Folder z filmami (domyślnie: {default_in})",
    )
    p.add_argument(
        "--output",
        type=Path,
        default=default_out,
        help=f"Folder docelowy z .jpg (domyślnie: {default_out})",
    )
    p.add_argument(
        "--every",
        type=int,
        default=15,
        help="Zapisuj co N-tą klatkę (większe N = mniej podobnych kadrów, szybciej etykietowanie)",
    )
    p.add_argument("--max-per-video", type=int, default=0, help="Limit klatek na jeden plik (0 = bez limitu)")
    args = p.parse_args()

    inp: Path = args.input
    out: Path = args.output
    if not inp.is_dir():
        raise SystemExit(f"Brak folderu wejściowego: {inp}\nUmieść tam pionowe nagrania lub podaj --input.")

    out.mkdir(parents=True, exist_ok=True)
    every = max(1, args.every)
    max_per = args.max_per_video

    videos = sorted(f for f in inp.iterdir() if f.is_file() and f.suffix.lower() in VIDEO_EXT)
    if not videos:
        raise SystemExit(f"W {inp} nie znaleziono plików wideo ({', '.join(sorted(VIDEO_EXT))}).")

    total_saved = 0
    for vpath in videos:
        cap = cv2.VideoCapture(str(vpath))
        if not cap.isOpened():
            print(f"Pomijam (nie można otworzyć): {vpath.name}")
            continue

        stem = vpath.stem.replace(" ", "_")
        saved_here = 0
        frame_i = 0
        while True:
            ok, frame = cap.read()
            if not ok:
                break
            if frame_i % every != 0:
                frame_i += 1
                continue
            if max_per and saved_here >= max_per:
                break
            name = f"{stem}_f{frame_i:06d}.jpg"
            dest = out / name
            cv2.imwrite(str(dest), frame, [cv2.IMWRITE_JPEG_QUALITY, 92])
            saved_here += 1
            total_saved += 1
            frame_i += 1

        cap.release()
        print(f"{vpath.name}: zapisano {saved_here} klatek → {out}")

    print(f"Razem: {total_saved} obrazów w {out}")


if __name__ == "__main__":
    main()
