"""WagaDlaŚwiń — backend (FastAPI).

Zawiera trzy moduły:

    yolo      — segmentacja YOLOv8-seg (ONNX) → maska + bbox.
    features  — wyciąganie cech geometrycznych z maski (OpenCV).
    xgb       — regresja masy (XGBoost) z cech.

Backend ma być uruchamiany z katalogu ``backend/`` jako ``app.main:app``.
"""

__all__ = ["yolo", "features", "xgb"]
