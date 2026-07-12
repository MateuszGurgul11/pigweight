"""YOLOv8-seg ONNX wrapper.

Ładuje ``pig-detector.onnx`` (ten sam model co frontend ma w
``web/public/models/``) i wystawia funkcję ``segment(image)``, która zwraca
maskę binarną w rozmiarze obrazu źródłowego oraz bbox.

Krok preprocessingu (letterbox 640x640) i postprocessing maski są zgodne z
ścieżką w `web/src/lib/detection.ts`, żeby cechy liczone przez backend
odpowiadały temu, co użytkownik widzi w przeglądarce.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import logging

import cv2
import numpy as np
import onnxruntime as ort

log = logging.getLogger("waga.yolo")

INPUT_SIZE = 640
MASK_COEFFS = 32
DEFAULT_CONF = 0.25
DEFAULT_MASK_THRESHOLD = 0.5


@dataclass
class Segmentation:
    """Wynik segmentacji w przestrzeni źródłowego obrazu."""

    mask: np.ndarray  # uint8 0/255, kształt (H, W) tożsamy z obrazem wejściowym
    bbox: tuple[int, int, int, int]  # (x, y, w, h) w pikselach źródła
    score: float


class YoloSegSession:
    def __init__(self, model_path: Path | str) -> None:
        model_path = Path(model_path)
        if not model_path.exists():
            raise FileNotFoundError(f"Brak modelu YOLO: {model_path}")
        self.session = ort.InferenceSession(
            str(model_path),
            providers=["CPUExecutionProvider"],
        )
        self.input_name = self.session.get_inputs()[0].name
        self.output_names = [o.name for o in self.session.get_outputs()]

    # ------------------------------------------------------------------
    # Pre/post helpers
    # ------------------------------------------------------------------
    @staticmethod
    def _letterbox(img: np.ndarray) -> tuple[np.ndarray, float, int, int]:
        """Skaluje obraz do INPUT_SIZE × INPUT_SIZE z czarnym wypełnieniem."""
        h, w = img.shape[:2]
        scale = min(INPUT_SIZE / w, INPUT_SIZE / h)
        nw, nh = int(round(w * scale)), int(round(h * scale))
        pad_x = (INPUT_SIZE - nw) // 2
        pad_y = (INPUT_SIZE - nh) // 2
        canvas = np.zeros((INPUT_SIZE, INPUT_SIZE, 3), dtype=np.uint8)
        resized = cv2.resize(img, (nw, nh), interpolation=cv2.INTER_LINEAR)
        canvas[pad_y : pad_y + nh, pad_x : pad_x + nw] = resized
        return canvas, scale, pad_x, pad_y

    @staticmethod
    def _detect_layout(dims: tuple[int, ...]) -> tuple[int, int, str]:
        # YOLOv8: (1, channels, anchors) lub (1, anchors, channels)
        if len(dims) != 3:
            raise ValueError(f"Niespodziewany kształt predykcji: {dims}")
        # mniejszy wymiar to channels, większy to anchors
        if dims[1] < dims[2]:
            return dims[1], dims[2], "ac"
        return dims[2], dims[1], "ca"

    @staticmethod
    def _read(data: np.ndarray, layout: str, channels: int, anchors: int,
              channel: int, anchor: int) -> float:
        if layout == "ac":
            return float(data[channel * anchors + anchor])
        return float(data[anchor * channels + channel])

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------
    def segment(
        self,
        image_bgr: np.ndarray,
        conf_threshold: float = DEFAULT_CONF,
    ) -> Optional[Segmentation]:
        """Zwraca segmentację albo ``None`` gdy nic nie wykryto."""
        if image_bgr.ndim != 3 or image_bgr.shape[2] != 3:
            raise ValueError("Oczekiwano obrazu BGR (HxWx3)")

        src_h, src_w = image_bgr.shape[:2]
        canvas, scale, pad_x, pad_y = self._letterbox(image_bgr)

        # BGR -> RGB, NCHW, [0, 1]
        rgb = cv2.cvtColor(canvas, cv2.COLOR_BGR2RGB).astype(np.float32) / 255.0
        tensor = np.transpose(rgb, (2, 0, 1))[None, ...]
        outputs = self.session.run(self.output_names, {self.input_name: tensor})

        # ---- Wybór tensora pred (3D) i proto (4D) ----
        pred = next((o for o in outputs if o.ndim == 3), None)
        proto = next((o for o in outputs if o.ndim == 4), None)

        if pred is None:
            return None

        pred = np.squeeze(pred, axis=0)  # (channels, anchors) lub (anchors, channels)
        # Przyjmujemy zawsze (channels, anchors) dla wygody
        if pred.shape[0] > pred.shape[1]:
            pred = pred.T
        channels, anchors = pred.shape

        # Liczba klas (zwykle 1 = "pig"); reszta to bbox(4) + maski(32 jeśli seg)
        has_proto = proto is not None
        n_mask = MASK_COEFFS if has_proto else 0
        n_classes = channels - 4 - n_mask
        if n_classes <= 0:
            return None

        cls_block = pred[4 : 4 + n_classes, :]  # (nc, anchors)
        scores = cls_block.max(axis=0)

        # Find all detections above threshold, pick the largest by bbox area
        above = np.where(scores >= conf_threshold)[0]
        if len(above) == 0:
            top_score = float(scores.max())
            log.info("YOLO no detection above threshold (best=%.4f, threshold=%.2f)", top_score, conf_threshold)
            return None

        bbox_areas = pred[2, above] * pred[3, above]  # w * h in letterbox space
        best_idx = int(above[np.argmax(bbox_areas)])
        best_score = float(scores[best_idx])
        log.info("YOLO selected: score=%.4f bbox_area=%.0f (%d candidates above threshold=%.2f)",
                 best_score, float(bbox_areas.max()), len(above), conf_threshold)

        cx, cy, bw, bh = pred[0:4, best_idx]
        # bbox w przestrzeni źródła
        x1 = (cx - bw / 2 - pad_x) / scale
        y1 = (cy - bh / 2 - pad_y) / scale
        x2 = (cx + bw / 2 - pad_x) / scale
        y2 = (cy + bh / 2 - pad_y) / scale
        x1 = max(0, int(round(x1)))
        y1 = max(0, int(round(y1)))
        x2 = min(src_w, int(round(x2)))
        y2 = min(src_h, int(round(y2)))
        bw_src = max(1, x2 - x1)
        bh_src = max(1, y2 - y1)

        # Maska binarna w rozmiarze źródła
        mask_src = np.zeros((src_h, src_w), dtype=np.uint8)

        if has_proto:
            coeffs = pred[4 + n_classes : 4 + n_classes + MASK_COEFFS, best_idx]
            proto_arr = np.squeeze(proto, axis=0)  # (32, mh, mw)
            _, mh, mw = proto_arr.shape
            # liniowa kombinacja prototypów
            combined = np.tensordot(coeffs, proto_arr, axes=1)  # (mh, mw)
            mask_proto = 1.0 / (1.0 + np.exp(-combined))
            mask_proto = (mask_proto > DEFAULT_MASK_THRESHOLD).astype(np.uint8) * 255

            # Skala proto -> input 640
            mask_input = cv2.resize(
                mask_proto, (INPUT_SIZE, INPUT_SIZE), interpolation=cv2.INTER_NEAREST
            )
            # Wytnij obszar realnego zdjęcia (bez paddingu) i przeskaluj do źródła
            inner = mask_input[pad_y : INPUT_SIZE - pad_y, pad_x : INPUT_SIZE - pad_x]
            if inner.size > 0:
                mask_src = cv2.resize(
                    inner, (src_w, src_h), interpolation=cv2.INTER_NEAREST
                )
            # Zostaw tylko piksele wewnątrz bboxa, żeby drobne artefakty z innych
            # świń w kadrze nie zafałszowały cech.
            box_mask = np.zeros_like(mask_src)
            box_mask[y1:y2, x1:x2] = 255
            mask_src = cv2.bitwise_and(mask_src, box_mask)
        else:
            # brak proto -> tylko bbox jako "maska"
            mask_src[y1:y2, x1:x2] = 255

        return Segmentation(
            mask=mask_src,
            bbox=(x1, y1, bw_src, bh_src),
            score=best_score,
        )


def mask_to_polygon(mask: np.ndarray) -> list[tuple[float, float]]:
    """Największy zewnętrzny kontur maski → uproszczony polygon (Douglas-Peucker)."""
    contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_NONE)
    if not contours:
        return []
    largest = max(contours, key=cv2.contourArea)
    epsilon = 0.005 * cv2.arcLength(largest, True)
    approx = cv2.approxPolyDP(largest, epsilon, True)
    return [(float(p[0][0]), float(p[0][1])) for p in approx]
