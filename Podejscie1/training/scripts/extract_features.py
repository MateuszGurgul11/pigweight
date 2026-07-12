#!/usr/bin/env python3
"""Wyciąga cechy geometryczne z masek PigRGB-Weight (gold) → CSV do treningu.

Struktura datasetu:

    training/datasets/PigRGB-Weight/RGB_MASK_3394/
    ├── MASK_3394/<kg>_<pig_id>/<kg>kg_<n>.png   — maski binarne
    └── RGB_3394/<kg>_<pig_id>/<kg>kg_<n>.png    — odpowiadające RGB (nieużywane tu)

Opcjonalnie, z flagą ``--include-pseudo``, dorzuca pseudo-maski wygenerowane
z YOLOv8-seg dla zdjęć z `RGB_9579/foldX/<kg>_<id>/`. To duża augmentacja
(9579 zdjęć), ale jakość masek zależy od modelu.

Uruchomienie:

    python training/scripts/extract_features.py
    python training/scripts/extract_features.py --include-pseudo

Wyjście: ``training/datasets/pigrgb_features.csv`` z kolumnami:
    pig_id, sample, source, weight_kg, <wszystkie cechy z FEATURE_ORDER>
"""
from __future__ import annotations

import argparse
import csv
import sys
from pathlib import Path
from typing import Iterator

import cv2
import numpy as np

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))  # żeby import "backend.app.features" działał

from backend.app.features import FEATURE_ORDER, MaskFeatures, extract_features  # noqa: E402


def imread_unicode(path: Path, flags: int) -> np.ndarray | None:
    """Wczytanie obrazu jak cv2.imread, ale działa ze ścieżkami Unicode na Windowsie.

    Domyślne cv2.imread przekazuje ścieżkę do warstwy C++ OpenCV, która często używa
    kodowania ANSI — wtedy np. ``WagaŚwiń`` w logu wygląda jak ``Waga┼Üwi┼ä`` i plik
    nie jest znajdowany.
    """
    try:
        buf = np.frombuffer(path.read_bytes(), dtype=np.uint8)
    except OSError:
        return None
    if buf.size == 0:
        return None
    return cv2.imdecode(buf, flags)


DATASET_ROOT = REPO_ROOT / "training" / "datasets" / "PigRGB-Weight"
GOLD_MASK_DIR = DATASET_ROOT / "RGB_MASK_3394" / "MASK_3394"
RGB9579_DIR = DATASET_ROOT / "RGB_9579"
DEFAULT_OUTPUT = REPO_ROOT / "training" / "datasets" / "pigrgb_features.csv"


def parse_folder_name(folder: str) -> tuple[float | None, int | None]:
    """`102.7_42` -> (102.7, 42). Zwraca None gdy parsowanie się nie udaje."""
    try:
        kg_str, pid_str = folder.split("_", 1)
        return float(kg_str), int(pid_str)
    except ValueError:
        return None, None


def iter_gold_masks() -> Iterator[tuple[Path, float, int, str]]:
    """Yielduje (path, kg, pig_id, sample_id) z RGB_MASK_3394/MASK_3394."""
    if not GOLD_MASK_DIR.is_dir():
        raise SystemExit(f"Brak katalogu masek gold: {GOLD_MASK_DIR}")
    for sub in sorted(GOLD_MASK_DIR.iterdir()):
        if not sub.is_dir():
            continue
        kg, pid = parse_folder_name(sub.name)
        if kg is None or pid is None:
            print(f"  pomijam {sub.name}: nieparsowalna nazwa")
            continue
        for png in sorted(sub.glob("*.png")):
            yield png, kg, pid, png.stem


def iter_pseudo_masks(yolo_session, conf: float = 0.25) -> Iterator[tuple[Path, np.ndarray, float, int, str]]:
    """Generuje pseudo-maski przez YOLOv8-seg dla RGB_9579."""
    if not RGB9579_DIR.is_dir():
        return
    for fold in sorted(RGB9579_DIR.iterdir()):
        if not fold.is_dir():
            continue
        for sub in sorted(fold.iterdir()):
            if not sub.is_dir():
                continue
            kg, pid = parse_folder_name(sub.name)
            if kg is None or pid is None:
                continue
            for png in sorted(sub.glob("*.png")):
                img = imread_unicode(png, cv2.IMREAD_COLOR)
                if img is None:
                    continue
                seg = yolo_session.segment(img, conf_threshold=conf)
                if seg is None:
                    continue
                yield png, seg.mask, kg, pid, png.stem


def write_csv(rows: list[dict], output: Path) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        raise SystemExit("Brak wierszy do zapisu — sprawdź dataset.")
    fieldnames = ["pig_id", "sample", "source", "weight_kg", *FEATURE_ORDER]
    with output.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        for r in rows:
            w.writerow(r)


def features_to_row(feats: MaskFeatures, *, weight_kg: float, pig_id: int,
                    sample: str, source: str) -> dict:
    row = {"pig_id": pig_id, "sample": sample, "source": source, "weight_kg": weight_kg}
    row.update(feats.to_dict())
    return row


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--output", type=Path, default=DEFAULT_OUTPUT,
                    help="Plik CSV wyjściowy")
    ap.add_argument("--include-pseudo", action="store_true",
                    help="Dorzuca cechy z pseudo-masek YOLO dla RGB_9579 (9579 zdjęć)")
    ap.add_argument("--yolo-model", type=Path,
                    default=REPO_ROOT / "backend" / "models" / "pig-detector.onnx",
                    help="ONNX YOLOv8-seg używany do pseudo-masek")
    ap.add_argument("--limit", type=int, default=0,
                    help="Maks. liczba próbek (0 = bez limitu) — do szybkich testów")
    args = ap.parse_args()

    rows: list[dict] = []
    print(f"[GOLD] {GOLD_MASK_DIR}")
    n_skipped = 0
    for path, kg, pid, sample in iter_gold_masks():
        mask = imread_unicode(path, cv2.IMREAD_GRAYSCALE)
        if mask is None:
            n_skipped += 1
            continue
        feats = extract_features(mask)
        if feats is None:
            n_skipped += 1
            continue
        rows.append(features_to_row(feats, weight_kg=kg, pig_id=pid, sample=sample, source="gold"))
        if args.limit and len(rows) >= args.limit:
            break
    print(f"  gold: {len(rows)} próbek (pominięto {n_skipped})")

    if args.include_pseudo and (not args.limit or len(rows) < args.limit):
        from backend.app.yolo import YoloSegSession  # lazy import (wymaga onnxruntime)
        yolo = YoloSegSession(args.yolo_model)
        print(f"[PSEUDO] {RGB9579_DIR}")
        n_pseudo = 0
        for _path, mask, kg, pid, sample in iter_pseudo_masks(yolo):
            feats = extract_features(mask)
            if feats is None:
                continue
            rows.append(features_to_row(feats, weight_kg=kg, pig_id=pid, sample=sample, source="pseudo"))
            n_pseudo += 1
            if args.limit and len(rows) >= args.limit:
                break
        print(f"  pseudo: {n_pseudo} próbek")

    write_csv(rows, args.output)
    print(f"Zapisano {len(rows)} wierszy do {args.output}")


if __name__ == "__main__":
    main()
