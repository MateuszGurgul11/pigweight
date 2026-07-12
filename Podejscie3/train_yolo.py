"""
Trening YOLOv8n-seg na datasecie z Roboflow.
Automatycznie tworzy split train/valid (80/20) i uruchamia trening.
"""
import os
import random
import shutil
from pathlib import Path

import yaml
from ultralytics import YOLO

SCRIPT_DIR = Path(os.path.abspath(__file__)).parent
DATASET_SRC = SCRIPT_DIR / "datasets" / "pig detection.yolov8"
DATASET_FIXED = SCRIPT_DIR / "datasets" / "pig_yolo_fixed"
MODEL_OUTPUT = SCRIPT_DIR / "models"

SEED = 42
VAL_RATIO = 0.15
EPOCHS = 80
IMG_SIZE = 640
BATCH = 4          # CPU — male batch
PATIENCE = 20      # early stopping


def prepare_split():
    """Tworzy folder pig_yolo_fixed z poprawnym podzialem train/val."""
    src_imgs = list((DATASET_SRC / "train" / "images").glob("*.jpg"))
    src_imgs += list((DATASET_SRC / "train" / "images").glob("*.png"))
    random.seed(SEED)
    random.shuffle(src_imgs)

    n_val = max(1, int(len(src_imgs) * VAL_RATIO))
    val_imgs = src_imgs[:n_val]
    train_imgs = src_imgs[n_val:]

    print(f"Dataset: {len(src_imgs)} obrazow  ->  train={len(train_imgs)}, val={len(val_imgs)}")

    for split, imgs in [("train", train_imgs), ("valid", val_imgs)]:
        img_dir = DATASET_FIXED / split / "images"
        lbl_dir = DATASET_FIXED / split / "labels"
        img_dir.mkdir(parents=True, exist_ok=True)
        lbl_dir.mkdir(parents=True, exist_ok=True)

        for img_path in imgs:
            lbl_path = DATASET_SRC / "train" / "labels" / (img_path.stem + ".txt")
            shutil.copy2(img_path, img_dir / img_path.name)
            if lbl_path.exists():
                shutil.copy2(lbl_path, lbl_dir / lbl_path.name)
            else:
                (lbl_dir / (img_path.stem + ".txt")).write_text("")

    data_yaml = {
        "path": str(DATASET_FIXED),
        "train": "train/images",
        "val": "valid/images",
        "nc": 1,
        "names": ["pig"],
    }
    yaml_path = DATASET_FIXED / "data.yaml"
    with open(yaml_path, "w") as f:
        yaml.dump(data_yaml, f, default_flow_style=False)

    print(f"data.yaml zapisany: {yaml_path}")
    return yaml_path


def train(yaml_path: Path):
    MODEL_OUTPUT.mkdir(exist_ok=True)
    model = YOLO("yolov8n-seg.pt")

    print("\nStart treningu YOLOv8n-seg")
    print(f"  Epochs={EPOCHS}, imgsz={IMG_SIZE}, batch={BATCH}")
    print(f"  Wyniki w: {MODEL_OUTPUT}\n")

    results = model.train(
        data=str(yaml_path),
        epochs=EPOCHS,
        imgsz=IMG_SIZE,
        batch=BATCH,
        patience=PATIENCE,
        device="cpu",
        project=str(MODEL_OUTPUT),
        name="pig_seg",
        exist_ok=True,
        verbose=True,
        plots=True,
        save=True,
        save_period=10,
    )
    return results


if __name__ == "__main__":
    yaml_path = prepare_split()
    results = train(yaml_path)

    best_pt = MODEL_OUTPUT / "pig_seg" / "weights" / "best.pt"
    if best_pt.exists():
        dest = SCRIPT_DIR / "models" / "pig_seg_best.pt"
        shutil.copy2(best_pt, dest)
        print(f"\nModel zapisany: {dest}")
    else:
        print("\nUWAGA: best.pt nie znaleziony w wynikach treningu")
