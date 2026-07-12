#!/usr/bin/env python3
"""Trening YOLOv8 Segmentation pod model „świnia z góry” + eksport ONNX.

Wymagania:
  pip install -r requirements.txt   (ultralytics)

Przed uruchomieniem upewnij się, że datasets/pig_top jest zbudowany:
  python scripts/prepare_dataset.py

Wyniki:
  runs/segment/pig_top_seg/weights/best.pt
  runs/segment/pig_top_seg/weights/best.onnx  (skopiuj do web/public/models/pig-detector.onnx)
"""
from __future__ import annotations

import argparse
import shutil
from pathlib import Path

from ultralytics import YOLO


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--weights", default="yolov8n-seg.pt", help="bazowy checkpoint")
    parser.add_argument("--epochs", type=int, default=120)
    parser.add_argument("--imgsz", type=int, default=640)
    parser.add_argument("--batch", type=int, default=16)
    parser.add_argument("--device", default=None, help="np. 0 dla GPU, cpu, mps")
    parser.add_argument(
        "--name",
        default="pig_top_seg",
        help="nazwa runu w runs/segment/<name>",
    )
    parser.add_argument(
        "--copy-to-web",
        action="store_true",
        help="po treningu kopiuje best.onnx do ../web/public/models/pig-detector.onnx",
    )
    args = parser.parse_args()

    root = Path(__file__).resolve().parent
    ds = root / "datasets" / "pig_top"
    data_yaml = ds / "data.yaml"
    if not data_yaml.exists():
        raise SystemExit(
            f"Brak {data_yaml}.\n"
            "Najpierw uruchom: python scripts/prepare_dataset.py"
        )

    for split in ("train", "val"):
        labels = ds / "labels" / split
        n = len(list(labels.glob("*.txt"))) if labels.is_dir() else 0
        if n == 0:
            raise SystemExit(
                f"Brak etykiet w {labels} (split: {split}).\n"
                "Uruchom: python scripts/prepare_dataset.py"
            )

    model = YOLO(args.weights)
    project_dir = root / "runs" / "segment"
    train_kwargs: dict = dict(
        data=str(data_yaml),
        epochs=args.epochs,
        imgsz=args.imgsz,
        batch=args.batch,
        project=str(project_dir),
        name=args.name,
        exist_ok=True,
        patience=30,
        cos_lr=True,
        seed=42,
        # Lekkie augmentacje — nie psują geometrii sylwetki (ważne dla powierzchni)
        hsv_h=0.01,
        hsv_s=0.5,
        hsv_v=0.4,
        degrees=10.0,
        translate=0.05,
        scale=0.3,
        shear=0.0,
        perspective=0.0,
        flipud=0.5,
        fliplr=0.5,
        mosaic=1.0,
        mixup=0.0,
    )
    if args.device is not None:
        train_kwargs["device"] = args.device

    model.train(**train_kwargs)

    best = root / "runs" / "segment" / args.name / "weights" / "best.pt"
    if not best.exists():
        raise SystemExit(f"Nie znaleziono best.pt: {best}")

    print(f"Najlepsze wagi: {best}")

    onnx_path = root / "runs" / "segment" / args.name / "weights" / "best.onnx"
    YOLO(str(best)).export(format="onnx", imgsz=args.imgsz, simplify=True, opset=12)
    print(f"Eksport ONNX: {onnx_path}")

    if args.copy_to_web:
        web_target = root.parent / "web" / "public" / "models" / "pig-detector.onnx"
        web_target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(onnx_path, web_target)
        print(f"Skopiowano do {web_target}")
    else:
        print(
            "Skopiuj ręcznie:\n"
            f"  {onnx_path}\n"
            "  -> web/public/models/pig-detector.onnx\n"
            "(albo uruchom z flagą --copy-to-web)"
        )


if __name__ == "__main__":
    main()
