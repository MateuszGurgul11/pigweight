"""FastAPI — endpoint inferencji dla aplikacji WagaDlaŚwiń.

Uruchomienie (z katalogu ``backend/``):

    uvicorn app.main:app --host 0.0.0.0 --port 8000

Endpoints:

    GET  /healthz          → status: {ok, hasYolo, hasXgb, version}
    POST /predict          → multipart image → {massKg, verdict, mask, dims, features}
    POST /calibrate        → multipart image + form mass_kg → zapisz bias modelu

Brak XGBoost lub YOLO nie wywala serwera — endpoint /predict zwraca błąd HTTP
i UI pokazuje komunikat „brak modelu wagi". Pozwala to wystartować backend
zanim trening się skończy.
"""
from __future__ import annotations

import collections
import io
import logging
import os
import time
from pathlib import Path
from typing import Optional

import cv2
import numpy as np
from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from PIL import Image

from .features import MaskFeatures, extract_features
from .xgb import WeightModel
from .yolo import Segmentation, YoloSegSession, mask_to_polygon

VERSION = "0.1.0"
log = logging.getLogger("waga.backend")
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

ROOT = Path(__file__).resolve().parents[1]
MODELS_DIR = Path(os.environ.get("WAGA_MODELS_DIR", ROOT / "models"))
YOLO_PATH = MODELS_DIR / "pig-detector.onnx"
XGB_PATH = MODELS_DIR / "pig_weight.json"
CALIB_PATH = MODELS_DIR / "calibration.json"


# ---------------------------------------------------------------------------
# Lazy singletons — żeby healthz odpowiadał nawet gdy modele nie są
# dostępne. Wczytujemy je przy pierwszym /predict.
# ---------------------------------------------------------------------------
_yolo: Optional[YoloSegSession] = None
_xgb: Optional[WeightModel] = None
_yolo_load_err: Optional[str] = None
_xgb_load_err: Optional[str] = None

SMOOTHING_WINDOW = int(os.environ.get("WAGA_SMOOTH_WINDOW", "5"))
OUTLIER_SIGMA = float(os.environ.get("WAGA_OUTLIER_SIGMA", "2.0"))
_recent_predictions: collections.deque[float] = collections.deque(maxlen=max(1, SMOOTHING_WINDOW))


def _load_yolo() -> Optional[YoloSegSession]:
    global _yolo, _yolo_load_err
    if _yolo is not None:
        return _yolo
    try:
        _yolo = YoloSegSession(YOLO_PATH)
        _yolo_load_err = None
        log.info("YOLO załadowany: %s", YOLO_PATH)
    except Exception as exc:  # noqa: BLE001 — chcemy każdy błąd pokazać
        _yolo_load_err = f"{type(exc).__name__}: {exc}"
        log.warning("Nie wczytano YOLO (%s): %s", YOLO_PATH, exc)
    return _yolo


def _load_xgb() -> Optional[WeightModel]:
    global _xgb, _xgb_load_err
    if _xgb is not None:
        return _xgb
    try:
        _xgb = WeightModel(XGB_PATH, CALIB_PATH)
        _xgb_load_err = None
        log.info("XGBoost załadowany: %s (bias=%.3f kg)", XGB_PATH, _xgb.bias_kg)
    except Exception as exc:  # noqa: BLE001
        _xgb_load_err = f"{type(exc).__name__}: {exc}"
        log.warning("Nie wczytano XGBoost (%s): %s", XGB_PATH, exc)
    return _xgb


# ---------------------------------------------------------------------------
# FastAPI
# ---------------------------------------------------------------------------
app = FastAPI(title="WagaDlaŚwiń backend", version=VERSION)

# CORS — UI w trybie dev (Vite) chodzi na :5173, na produkcji backend serwuje
# build statyczny tym samym hostem; dla bezpieczeństwa zostawiamy *.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)


class HealthResponse(BaseModel):
    ok: bool
    hasYolo: bool
    hasXgb: bool
    version: str
    yoloError: Optional[str] = None
    xgbError: Optional[str] = None
    biasKg: float = 0.0


class BBox(BaseModel):
    x: int
    y: int
    w: int
    h: int


class MaskOut(BaseModel):
    polygon: list[list[float]]
    areaPx: float
    bbox: BBox


class Dims(BaseModel):
    lengthPx: float
    widthPx: float
    lengthCm: float
    widthCm: float
    areaCm2: float


class PredictResponse(BaseModel):
    massKg: float
    massRawKg: float
    verdict: str
    score: float
    mask: MaskOut
    dims: Dims
    features: dict
    elapsedMs: float


class CalibrateResponse(BaseModel):
    biasKg: float
    samples: int
    predictedKg: float
    knownKg: float


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _smooth_prediction(raw_kg: float) -> float:
    """Uśrednia predykcję z buforem ostatnich N pomiarów.

    Odrzuca outliersy (> OUTLIER_SIGMA * std od mediany) i zwraca średnią
    z pozostałych. Gdy bufor jest pusty lub za mały — zwraca raw_kg.
    """
    _recent_predictions.append(raw_kg)
    buf = list(_recent_predictions)
    if len(buf) < 2:
        return raw_kg
    median = float(np.median(buf))
    std = float(np.std(buf))
    if std < 0.1:
        return float(np.mean(buf))
    filtered = [v for v in buf if abs(v - median) <= OUTLIER_SIGMA * std]
    if not filtered:
        return raw_kg
    return float(np.mean(filtered))


def _classify_verdict(mass_kg: float, target_min: float, target_max: float,
                      margin_thin: float, margin_fat: float) -> str:
    if mass_kg < target_min - margin_thin:
        return "thin"
    if mass_kg > target_max + margin_fat:
        return "fat"
    return "ok"


def _decode_image(blob: bytes) -> np.ndarray:
    arr = np.frombuffer(blob, dtype=np.uint8)
    img = cv2.imdecode(arr, cv2.IMREAD_COLOR)
    if img is None:
        # Pillow fallback (niektóre PNG / WebP)
        try:
            pil = Image.open(io.BytesIO(blob)).convert("RGB")
            img = cv2.cvtColor(np.array(pil), cv2.COLOR_RGB2BGR)
        except Exception as exc:  # noqa: BLE001
            raise HTTPException(status_code=400, detail=f"Nie udało się zdekodować obrazu: {exc}")
    return img


def _segment_or_400(yolo: YoloSegSession, image: np.ndarray, conf: float) -> Segmentation:
    seg = yolo.segment(image, conf_threshold=conf)
    if seg is None:
        raise HTTPException(status_code=422, detail="Brak detekcji świni w kadrze")
    return seg


def _features_or_400(
    seg: Segmentation, px_per_cm: float, camera_height_cm: float,
    depth_map: Optional[np.ndarray] = None,
) -> MaskFeatures:
    feats = extract_features(
        seg.mask, px_per_cm=px_per_cm, camera_height_cm=camera_height_cm,
        depth_map=depth_map,
    )
    if feats is None:
        raise HTTPException(status_code=422, detail="Maska zbyt mała / pusta")
    return feats


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------
@app.get("/healthz", response_model=HealthResponse)
def healthz() -> HealthResponse:
    yolo = _load_yolo()
    xgbm = _load_xgb()
    return HealthResponse(
        ok=True,
        hasYolo=yolo is not None,
        hasXgb=xgbm is not None,
        version=VERSION,
        yoloError=_yolo_load_err,
        xgbError=_xgb_load_err,
        biasKg=xgbm.bias_kg if xgbm else 0.0,
    )


@app.post("/predict", response_model=PredictResponse)
async def predict(
    image: UploadFile = File(...),
    depth: Optional[UploadFile] = File(None),
    target_min_kg: float = Form(90.0),
    target_max_kg: float = Form(110.0),
    margin_thin_kg: float = Form(0.0),
    margin_fat_kg: float = Form(0.0),
    confidence_threshold: float = Form(0.25),
    px_per_cm: float = Form(0.0),
    camera_height_cm: float = Form(180.0),
    smooth: bool = Form(True),
) -> PredictResponse:
    yolo = _load_yolo()
    if yolo is None:
        raise HTTPException(status_code=503, detail=f"YOLO niedostępny: {_yolo_load_err}")
    xgbm = _load_xgb()
    if xgbm is None:
        raise HTTPException(status_code=503, detail=f"XGBoost niedostępny: {_xgb_load_err}")

    blob = await image.read()
    img = _decode_image(blob)

    depth_map: Optional[np.ndarray] = None
    if depth is not None:
        depth_blob = await depth.read()
        depth_map = np.frombuffer(depth_blob, dtype=np.uint16).reshape(img.shape[:2])

    started = time.perf_counter()
    seg = _segment_or_400(yolo, img, confidence_threshold)
    feats = _features_or_400(seg, px_per_cm=px_per_cm, camera_height_cm=camera_height_cm,
                             depth_map=depth_map)
    mass_raw = xgbm.predict(feats)
    mass_kg = _smooth_prediction(mass_raw) if smooth else mass_raw
    verdict = _classify_verdict(mass_kg, target_min_kg, target_max_kg, margin_thin_kg, margin_fat_kg)
    elapsed_ms = (time.perf_counter() - started) * 1000

    polygon = mask_to_polygon(seg.mask)
    bx, by, bw, bh = seg.bbox
    return PredictResponse(
        massKg=round(mass_kg, 2),
        massRawKg=round(mass_raw, 2),
        verdict=verdict,
        score=round(seg.score, 3),
        mask=MaskOut(
            polygon=[[float(x), float(y)] for x, y in polygon],
            areaPx=feats.area_px,
            bbox=BBox(x=bx, y=by, w=bw, h=bh),
        ),
        dims=Dims(
            lengthPx=feats.length_px,
            widthPx=feats.width_px,
            lengthCm=feats.length_cm,
            widthCm=feats.width_cm,
            areaCm2=feats.area_cm2,
        ),
        features=feats.to_dict(),
        elapsedMs=round(elapsed_ms, 1),
    )


@app.post("/predict/reset")
def predict_reset() -> dict:
    """Czyści bufor smoothing — wywołaj gdy zmienia się świnia w kadrze."""
    _recent_predictions.clear()
    return {"cleared": True}


@app.post("/calibrate", response_model=CalibrateResponse)
async def calibrate(
    image: UploadFile = File(...),
    mass_kg: float = Form(...),
    px_per_cm: float = Form(0.0),
    camera_height_cm: float = Form(180.0),
    confidence_threshold: float = Form(0.25),
) -> CalibrateResponse:
    """Dostraja ``bias_kg`` modelu na podstawie świni o znanej wadze.

    Strategia minimalna: bias = known − raw_predict. Po wielu kalibracjach
    nadpisujemy poprzednie wartości — UI powinien pokazać wszystkie próbki
    i pozwolić użytkownikowi uśrednić w razie potrzeby.
    """
    yolo = _load_yolo()
    if yolo is None:
        raise HTTPException(status_code=503, detail=f"YOLO niedostępny: {_yolo_load_err}")
    xgbm = _load_xgb()
    if xgbm is None:
        raise HTTPException(status_code=503, detail=f"XGBoost niedostępny: {_xgb_load_err}")
    if mass_kg <= 0 or mass_kg > 500:
        raise HTTPException(status_code=400, detail="Nieprawidłowa masa")

    blob = await image.read()
    img = _decode_image(blob)
    seg = _segment_or_400(yolo, img, confidence_threshold)
    feats = _features_or_400(seg, px_per_cm=px_per_cm, camera_height_cm=camera_height_cm)
    raw = xgbm.predict_raw(feats)
    new_bias = float(mass_kg - raw)
    xgbm.save_calibration(new_bias, samples=1)
    log.info("Kalibracja: known=%.2f raw=%.2f → bias=%.3f", mass_kg, raw, new_bias)
    return CalibrateResponse(
        biasKg=new_bias,
        samples=1,
        predictedKg=round(raw, 2),
        knownKg=float(mass_kg),
    )


@app.get("/")
def root() -> dict:
    return {"app": "WagaDlaŚwiń backend", "version": VERSION, "endpoints": ["/healthz", "/predict", "/calibrate"]}
