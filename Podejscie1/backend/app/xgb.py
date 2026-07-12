"""XGBoost regressor wrapper.

Ładuje wytrenowany model (``pig_weight.json`` z ``training/train_xgboost.py``)
i wykonuje predykcję wagi z wektora cech. Trzyma też mały bias per-chlewnia
zapisany w ``calibration.json`` — pozwala dostroić model do konkretnej farmy
po zważeniu kilku świń (endpoint ``/calibrate``).

Obsługuje zarówno modele trenowane na surowych wagach (kg) jak i na
log1p-transformowanych wagach. Tryb wykrywany jest z calibration.json
(klucz ``use_log_transform``) lub automatycznie z metadanych modelu.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Optional

import numpy as np
import xgboost as xgb

from .features import FEATURE_ORDER, MaskFeatures


class WeightModel:
    def __init__(self, model_path: Path, calibration_path: Optional[Path] = None) -> None:
        if not model_path.exists():
            raise FileNotFoundError(f"Brak modelu XGBoost: {model_path}")
        self.booster = xgb.Booster()
        self.booster.load_model(str(model_path))
        self.calibration_path = calibration_path
        self.bias_kg = 0.0
        self.use_log_transform = True
        self._load_calibration()

    def _load_calibration(self) -> None:
        if self.calibration_path is None or not self.calibration_path.exists():
            return
        try:
            data = json.loads(self.calibration_path.read_text(encoding="utf-8"))
            self.bias_kg = float(data.get("bias_kg", 0.0))
            self.use_log_transform = bool(data.get("use_log_transform", True))
        except (OSError, ValueError, TypeError):
            self.bias_kg = 0.0

    def save_calibration(self, bias_kg: float, samples: int) -> None:
        if self.calibration_path is None:
            return
        self.calibration_path.parent.mkdir(parents=True, exist_ok=True)
        self.calibration_path.write_text(
            json.dumps({
                "bias_kg": float(bias_kg),
                "samples": int(samples),
                "use_log_transform": self.use_log_transform,
            }, indent=2),
            encoding="utf-8",
        )
        self.bias_kg = float(bias_kg)

    def _raw_predict(self, features: MaskFeatures) -> float:
        vec = features.to_vector().reshape(1, -1)
        dmat = xgb.DMatrix(vec, feature_names=FEATURE_ORDER)
        pred = float(self.booster.predict(dmat)[0])
        if self.use_log_transform:
            pred = float(np.expm1(pred))
        return pred

    def predict(self, features: MaskFeatures) -> float:
        kg = self._raw_predict(features) + self.bias_kg
        return max(0.0, kg)

    def predict_raw(self, features: MaskFeatures) -> float:
        return self._raw_predict(features)
