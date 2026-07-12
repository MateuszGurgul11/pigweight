#!/usr/bin/env python3
"""Buduje datasets/pig_top z eksportu Roboflow (segmentacja YOLOv8).

Kopiuje obrazy + etykiety z `roboflow/train/{images,labels}` do
`training/datasets/pig_top/{images,labels}/{train,val}` z deterministycznym
podziałem (domyślnie 85/15, ziarno losowe stałe).

Etykiety w formacie YOLO Segmentation (klasa + lista par x y, znormalizowane 0-1) —
nie modyfikujemy ich, tylko rozdzielamy.

Użycie:
  python scripts/prepare_dataset.py
  python scripts/prepare_dataset.py --val-ratio 0.2 --seed 7
"""
from __future__ import annotations

import argparse
import random
import shutil
from pathlib import Path

IMG_EXT = {".jpg", ".jpeg", ".png", ".bmp", ".webp"}


def find_repo_root(start: Path) -> Path:
    cur = start
    for _ in range(6):
        if (cur / "roboflow").is_dir() and (cur / "training").is_dir():
            return cur
        cur = cur.parent
    raise SystemExit(
        "Nie znaleziono katalogu repo (spodziewam się katalogów `roboflow/` i `training/`)."
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--val-ratio", type=float, default=0.15)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument(
        "--src",
        type=Path,
        default=None,
        help="Katalog źródłowy z eksportem Roboflow (domyślnie: <repo>/roboflow).",
    )
    parser.add_argument(
        "--dst",
        type=Path,
        default=None,
        help="Katalog docelowy (domyślnie: <repo>/training/datasets/pig_top).",
    )
    parser.add_argument(
        "--copy",
        action="store_true",
        help="Kopiuj pliki zamiast tworzyć kopie zapasowe (domyślnie kopiuje).",
    )
    args = parser.parse_args()

    here = Path(__file__).resolve()
    repo = find_repo_root(here.parent)
    src_root: Path = args.src or (repo / "roboflow")
    dst_root: Path = args.dst or (repo / "training" / "datasets" / "pig_top")

    src_img = src_root / "train" / "images"
    src_lbl = src_root / "train" / "labels"
    if not src_img.is_dir() or not src_lbl.is_dir():
        raise SystemExit(
            f"Brak plików źródłowych. Oczekiwano:\n  {src_img}\n  {src_lbl}\n"
            "Wyeksportuj z Roboflow w formacie YOLOv8 i rozpakuj do katalogu `roboflow/`."
        )

    images = sorted(p for p in src_img.iterdir() if p.suffix.lower() in IMG_EXT)
    if not images:
        raise SystemExit(f"Brak obrazów w {src_img}")

    pairs: list[tuple[Path, Path]] = []
    missing: list[str] = []
    for img in images:
        lbl = src_lbl / (img.stem + ".txt")
        if lbl.is_file():
            pairs.append((img, lbl))
        else:
            missing.append(img.name)

    if missing:
        print(f"UWAGA: {len(missing)} obrazów bez etykiet — pomijam (np. {missing[:3]}).")

    rnd = random.Random(args.seed)
    rnd.shuffle(pairs)
    n_val = max(1, int(round(len(pairs) * args.val_ratio)))
    val_pairs = pairs[:n_val]
    train_pairs = pairs[n_val:]
    if not train_pairs:
        raise SystemExit("Za mało plików, żeby zostawić cokolwiek do treningu.")

    splits = {
        "train": train_pairs,
        "val": val_pairs,
    }

    for split, pair_list in splits.items():
        img_dst = dst_root / "images" / split
        lbl_dst = dst_root / "labels" / split
        if img_dst.exists():
            shutil.rmtree(img_dst)
        if lbl_dst.exists():
            shutil.rmtree(lbl_dst)
        img_dst.mkdir(parents=True, exist_ok=True)
        lbl_dst.mkdir(parents=True, exist_ok=True)
        for img, lbl in pair_list:
            shutil.copy2(img, img_dst / img.name)
            shutil.copy2(lbl, lbl_dst / lbl.name)

    n_classes = _peek_class_count(splits["train"])

    # Nadpisujemy data.yaml ze ścieżką absolutną — Ultralytics ma globalny "dataset root"
    # (zwykle ~/datasets) i potrafi interpretować względne path: nieintuicyjnie.
    data_yaml = dst_root / "data.yaml"
    data_yaml.write_text(
        "# Wygenerowane przez scripts/prepare_dataset.py — ścieżki absolutne, żeby Ultralytics\n"
        "# nie szukał plików w globalnym dataset_root (np. ~/datasets).\n"
        f"path: {dst_root.as_posix()}\n"
        "train: images/train\n"
        "val: images/val\n"
        "nc: 1\n"
        "names:\n"
        "  0: pig\n",
        encoding="utf-8",
    )

    print("Gotowe.")
    print(f"  train: {len(train_pairs)} par (obraz + .txt) -> {dst_root / 'images' / 'train'}")
    print(f"  val:   {len(val_pairs)} par                 -> {dst_root / 'images' / 'val'}")
    print(f"  klasy w etykietach (unikalne ID): {sorted(n_classes)}")
    print(f"  data.yaml: {data_yaml}")


def _peek_class_count(pairs: list[tuple[Path, Path]]) -> set[int]:
    found: set[int] = set()
    for _, lbl in pairs[:50]:
        try:
            for line in lbl.read_text().splitlines():
                line = line.strip()
                if not line:
                    continue
                first = line.split()[0]
                found.add(int(first))
        except (ValueError, OSError):
            continue
    return found


if __name__ == "__main__":
    main()
