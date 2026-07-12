#!/usr/bin/env python3
"""Extract features from OAK-D S2 dataset (RGB video + depth + YOLO segmentation).

Dataset structure:
    dataset/
    ├── calibration/camera_height_cm.txt
    ├── pig_001/
    │   ├── rgb_video.mp4
    │   ├── depth_frames.npy   (N, 1080, 1920) uint16 mm
    │   └── weight_kg.txt
    └── ...

For each pig, samples N frames evenly, runs YOLO segmentation on the RGB frame,
then extracts geometric + depth features using the aligned depth map.

Output: training/datasets/oakd_features.csv
"""
from __future__ import annotations

import argparse
import csv
import sys
from pathlib import Path

import cv2
import numpy as np

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

from backend.app.features import FEATURE_ORDER, extract_features  # noqa: E402
from backend.app.yolo import YoloSegSession  # noqa: E402

DATASET_DIR = Path(r"D:\Programowanie\WagaŚwiń\dataset")
DEFAULT_OUTPUT = REPO_ROOT / "training" / "datasets" / "oakd_features.csv"
DEFAULT_MODEL = REPO_ROOT / "backend" / "models" / "pig-detector.onnx"


def get_camera_height() -> float:
    path = DATASET_DIR / "calibration" / "camera_height_cm.txt"
    return float(path.read_text().strip())


def process_pig(
    pig_dir: Path,
    yolo: YoloSegSession,
    camera_height_cm: float,
    max_frames: int,
    conf: float,
) -> list[dict]:
    weight_path = pig_dir / "weight_kg.txt"
    video_path = pig_dir / "rgb_video.mp4"
    depth_path = pig_dir / "depth_frames.npy"

    if not weight_path.exists() or not video_path.exists():
        return []

    weight_kg = float(weight_path.read_text().strip())
    pig_id = pig_dir.name

    has_depth = depth_path.exists()
    depth_data = np.load(str(depth_path), mmap_mode="r") if has_depth else None

    cap = cv2.VideoCapture(str(video_path))
    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))

    if total_frames <= 0:
        cap.release()
        return []

    sample_count = min(max_frames, total_frames)
    indices = np.linspace(0, total_frames - 1, sample_count, dtype=int)
    indices = sorted(set(indices))

    rows = []
    for frame_idx in indices:
        cap.set(cv2.CAP_PROP_POS_FRAMES, frame_idx)
        ret, frame = cap.read()
        if not ret:
            continue

        seg = yolo.segment(frame, conf_threshold=conf)
        if seg is None:
            continue

        depth_frame = None
        if has_depth and frame_idx < depth_data.shape[0]:
            depth_frame = np.array(depth_data[frame_idx])

        px_per_cm = 0.0
        if camera_height_cm > 0 and depth_frame is not None:
            mask_pixels = seg.mask > 0
            depth_in_mask = depth_frame[mask_pixels].astype(np.float64)
            valid_depth = depth_in_mask[depth_in_mask > 0]
            if len(valid_depth) > 10:
                mean_depth_mm = float(valid_depth.mean())
                object_dist_cm = mean_depth_mm / 10.0
                h_img, w_img = frame.shape[:2]
                hfov_rad = np.radians(71.86)
                fov_width_cm = 2 * object_dist_cm * np.tan(hfov_rad / 2)
                px_per_cm = w_img / fov_width_cm if fov_width_cm > 0 else 0.0

        feats = extract_features(
            seg.mask,
            px_per_cm=px_per_cm,
            camera_height_cm=camera_height_cm,
            depth_map=depth_frame,
        )
        if feats is None:
            continue

        row = {"pig_id": pig_id, "sample": f"{pig_id}_f{frame_idx:04d}",
               "source": "oakd", "weight_kg": weight_kg}
        row.update(feats.to_dict())
        rows.append(row)

    cap.release()
    return rows


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    ap.add_argument("--model", type=Path, default=DEFAULT_MODEL)
    ap.add_argument("--max-frames", type=int, default=30,
                    help="Max frames to sample per pig video")
    ap.add_argument("--conf", type=float, default=0.10)
    args = ap.parse_args()

    camera_height_cm = get_camera_height()
    print(f"Camera height: {camera_height_cm} cm")

    yolo = YoloSegSession(args.model)
    print(f"YOLO model: {args.model}")

    pig_dirs = sorted(DATASET_DIR.glob("pig_*"))
    print(f"Found {len(pig_dirs)} pig directories")

    all_rows: list[dict] = []
    for pig_dir in pig_dirs:
        rows = process_pig(pig_dir, yolo, camera_height_cm, args.max_frames, args.conf)
        print(f"  {pig_dir.name}: {len(rows)} samples"
              f" (depth={'yes' if (pig_dir / 'depth_frames.npy').exists() else 'no'})")
        all_rows.extend(rows)

    if not all_rows:
        raise SystemExit("No samples extracted!")

    args.output.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = ["pig_id", "sample", "source", "weight_kg", *FEATURE_ORDER]
    with args.output.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        for r in all_rows:
            w.writerow(r)

    print(f"\nSaved {len(all_rows)} rows to {args.output}")
    unique_pigs = set(r["pig_id"] for r in all_rows)
    print(f"Unique pigs: {len(unique_pigs)}")
    has_depth = sum(1 for r in all_rows if r.get("depth_mean_mm", 0) > 0)
    print(f"Rows with depth: {has_depth}/{len(all_rows)}")


if __name__ == "__main__":
    main()
