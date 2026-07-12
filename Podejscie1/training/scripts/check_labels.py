#!/usr/bin/env python3
"""Sprawdza pary obraz ↔ etykieta YOLO w datasets/pig_top."""
from __future__ import annotations

from pathlib import Path

IMG_EXT = {".jpg", ".jpeg", ".png", ".bmp", ".webp"}


def main() -> None:
    training = Path(__file__).resolve().parent.parent
    ds = training / "datasets" / "pig_top"
    img_dir = ds / "images" / "train"
    lbl_dir = ds / "labels" / "train"

    if not img_dir.is_dir():
        raise SystemExit(f"Brak folderu: {img_dir}")

    images = sorted(p for p in img_dir.iterdir() if p.suffix.lower() in IMG_EXT)
    lbl_dir.mkdir(parents=True, exist_ok=True)
    labels = {p.stem for p in lbl_dir.glob("*.txt")}

    missing_txt: list[str] = []
    for img in images:
        if img.stem not in labels:
            missing_txt.append(img.name)

    extra_txt = sorted(labels - {p.stem for p in images})

    print(f"Obrazy w images/train: {len(images)}")
    print(f"Etykiety w labels/train: {len(labels)}")
    print(f"Brak .txt dla obrazu: {len(missing_txt)}")
    if missing_txt:
        print("\nPierwsze brakujące (max 15):")
        for n in missing_txt[:15]:
            print(f"  - {n}")
        if len(missing_txt) > 15:
            print(f"  ... i {len(missing_txt) - 15} więcej")

    if extra_txt:
        print(f"\nPliki .txt bez pary obrazu (max 10): {len(extra_txt)}")
        for s in extra_txt[:10]:
            print(f"  - {s}.txt")

    if not missing_txt and images:
        print("\nOK — każdy obraz ma etykietę. Możesz uruchomić: python train_yolo.py")
        raise SystemExit(0)

    if images and missing_txt:
        print(
            "\nNastępny krok: oznacz bboxy w Roboflow/CVAT, wyeksportuj YOLOv8 i skopiuj pliki "
            "z train/labels/ do datasets/pig_top/labels/train/ (nazwy .txt = nazwy .jpg).",
        )
    raise SystemExit(1 if missing_txt else 0)


if __name__ == "__main__":
    main()
