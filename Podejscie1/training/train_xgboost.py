#!/usr/bin/env python3
"""Trening XGBoost regresji wagi świni z cech geometrycznych.

Kolejność użycia:

    1. python scripts/extract_features.py
       (lub --include-pseudo dla 9579 dodatkowych zdjęć)
    2. python train_xgboost.py --copy-to-backend

Podział train/val jest grupowany po `pig_id`, żeby ten sam osobnik nie był
w obu zbiorach (data leakage zawyżyłby metryki).

Ulepszenia vs wersja bazowa:
    - GroupKFold (5-fold) zamiast single split — stabilniejsza ocena
    - Log-transform targetu (waga) — redukuje wpływ outliersów
    - Bayesian hyperparameter search (optuna) gdy --tune
    - Opcjonalny stacking z LightGBM (--stack)
    - Feature importance + residuals plot

Wynik:

    training/runs/xgb/pig_weight.json   — model XGBoost (booster JSON)
    training/runs/xgb/metrics.json      — MAE, MAPE, RMSE, R2 (CV mean ± std)
    training/runs/xgb/feature_importance.csv
    training/runs/xgb/residuals.png
"""
from __future__ import annotations

import argparse
import json
import shutil
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import xgboost as xgb
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score
from sklearn.model_selection import GroupKFold, GroupShuffleSplit

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from backend.app.features import FEATURE_ORDER  # noqa: E402

DEFAULT_CSV = REPO_ROOT / "training" / "datasets" / "pigrgb_features.csv"
DEFAULT_OUT = REPO_ROOT / "training" / "runs" / "xgb"
BACKEND_MODEL = REPO_ROOT / "backend" / "models" / "pig_weight.json"


def evaluate(y_true: np.ndarray, y_pred: np.ndarray) -> dict:
    mae = float(mean_absolute_error(y_true, y_pred))
    rmse = float(np.sqrt(mean_squared_error(y_true, y_pred)))
    mape = float(np.mean(np.abs((y_true - y_pred) / np.clip(y_true, 1e-3, None))) * 100)
    r2 = float(r2_score(y_true, y_pred))
    return {"mae_kg": mae, "rmse_kg": rmse, "mape_pct": mape, "r2": r2}


def train_single_xgb(
    X_train: np.ndarray, y_train: np.ndarray,
    X_val: np.ndarray, y_val: np.ndarray,
    params: dict, n_estimators: int, early_stopping: int,
    use_log: bool = True, verbose: bool = True,
) -> tuple[xgb.Booster, np.ndarray]:
    if use_log:
        y_tr = np.log1p(y_train)
        y_v = np.log1p(y_val)
    else:
        y_tr, y_v = y_train, y_val

    dtrain = xgb.DMatrix(X_train, label=y_tr, feature_names=FEATURE_ORDER)
    dval = xgb.DMatrix(X_val, label=y_v, feature_names=FEATURE_ORDER)

    booster = xgb.train(
        params,
        dtrain,
        num_boost_round=n_estimators,
        evals=[(dtrain, "train"), (dval, "val")],
        early_stopping_rounds=early_stopping,
        verbose_eval=100 if verbose else 0,
    )

    pred_val = booster.predict(dval)
    if use_log:
        pred_val = np.expm1(pred_val)

    return booster, pred_val


def run_cv(
    X: np.ndarray, y: np.ndarray, groups: np.ndarray,
    params: dict, n_folds: int, n_estimators: int,
    early_stopping: int, use_log: bool, verbose: bool = True,
) -> tuple[list[dict], np.ndarray, np.ndarray]:
    gkf = GroupKFold(n_splits=n_folds)
    fold_metrics = []
    oof_pred = np.zeros(len(y))
    oof_mask = np.zeros(len(y), dtype=bool)

    for fold_i, (train_idx, val_idx) in enumerate(gkf.split(X, y, groups)):
        if verbose:
            print(f"\n--- Fold {fold_i + 1}/{n_folds} "
                  f"(train={len(train_idx)}, val={len(val_idx)}) ---")
        _, pred_val = train_single_xgb(
            X[train_idx], y[train_idx],
            X[val_idx], y[val_idx],
            params, n_estimators, early_stopping,
            use_log=use_log, verbose=verbose,
        )
        oof_pred[val_idx] = pred_val
        oof_mask[val_idx] = True
        m = evaluate(y[val_idx], pred_val)
        fold_metrics.append(m)
        if verbose:
            print(f"  Fold {fold_i + 1}: MAE={m['mae_kg']:.2f} kg  "
                  f"RMSE={m['rmse_kg']:.2f} kg  MAPE={m['mape_pct']:.1f}%  R2={m['r2']:.3f}")

    return fold_metrics, oof_pred, oof_mask


def tune_hyperparams(
    X: np.ndarray, y: np.ndarray, groups: np.ndarray,
    n_folds: int, n_trials: int, use_log: bool, seed: int,
) -> dict:
    try:
        import optuna
        optuna.logging.set_verbosity(optuna.logging.WARNING)
    except ImportError:
        print("optuna niezainstalowane — używam domyślnych hiperparametrów.")
        print("  pip install optuna")
        return {}

    def objective(trial: optuna.Trial) -> float:
        params = {
            "objective": "reg:squarederror",
            "eval_metric": "mae",
            "learning_rate": trial.suggest_float("lr", 0.01, 0.2, log=True),
            "max_depth": trial.suggest_int("max_depth", 3, 10),
            "subsample": trial.suggest_float("subsample", 0.6, 1.0),
            "colsample_bytree": trial.suggest_float("colsample_bytree", 0.5, 1.0),
            "min_child_weight": trial.suggest_int("min_child_weight", 1, 20),
            "reg_lambda": trial.suggest_float("reg_lambda", 0.01, 10.0, log=True),
            "reg_alpha": trial.suggest_float("reg_alpha", 1e-4, 5.0, log=True),
            "gamma": trial.suggest_float("gamma", 0.0, 5.0),
            "seed": seed,
            "verbosity": 0,
        }
        fold_metrics, _, _ = run_cv(
            X, y, groups, params,
            n_folds=n_folds, n_estimators=1500,
            early_stopping=50, use_log=use_log, verbose=False,
        )
        mean_mae = float(np.mean([m["mae_kg"] for m in fold_metrics]))
        return mean_mae

    study = optuna.create_study(direction="minimize",
                                sampler=optuna.samplers.TPESampler(seed=seed))
    study.optimize(objective, n_trials=n_trials, show_progress_bar=True)

    print(f"\nNajlepszy trial: MAE={study.best_value:.2f} kg")
    print(f"  Parametry: {study.best_params}")
    return study.best_params


def train_lightgbm_stack(
    X: np.ndarray, y: np.ndarray, groups: np.ndarray,
    xgb_oof: np.ndarray, n_folds: int, seed: int,
) -> tuple[float, float]:
    """Trenuje LightGBM na cechach + predykcji XGBoost (stacking)."""
    try:
        import lightgbm as lgb
    except ImportError:
        print("lightgbm niezainstalowane — pomijam stacking.")
        print("  pip install lightgbm")
        return 0.0, 0.0

    X_stack = np.column_stack([X, xgb_oof.reshape(-1, 1)])
    gkf = GroupKFold(n_splits=n_folds)
    maes = []

    for train_idx, val_idx in gkf.split(X_stack, y, groups):
        dtrain = lgb.Dataset(X_stack[train_idx], label=np.log1p(y[train_idx]))
        dval = lgb.Dataset(X_stack[val_idx], label=np.log1p(y[val_idx]), reference=dtrain)
        params_lgb = {
            "objective": "regression",
            "metric": "mae",
            "learning_rate": 0.05,
            "num_leaves": 31,
            "subsample": 0.8,
            "colsample_bytree": 0.8,
            "min_child_samples": 5,
            "seed": seed,
            "verbose": -1,
        }
        model = lgb.train(
            params_lgb, dtrain,
            num_boost_round=500,
            valid_sets=[dval],
            callbacks=[lgb.early_stopping(30, verbose=False)],
        )
        pred = np.expm1(model.predict(X_stack[val_idx]))
        maes.append(float(mean_absolute_error(y[val_idx], pred)))

    mean_mae = float(np.mean(maes))
    std_mae = float(np.std(maes))
    print(f"\nStacking LightGBM: MAE={mean_mae:.2f} ± {std_mae:.2f} kg")
    return mean_mae, std_mae


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--csv", type=Path, default=DEFAULT_CSV)
    ap.add_argument("--out", type=Path, default=DEFAULT_OUT)
    ap.add_argument("--n-folds", type=int, default=5)
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--n-estimators", type=int, default=1200)
    ap.add_argument("--max-depth", type=int, default=6)
    ap.add_argument("--lr", type=float, default=0.05)
    ap.add_argument("--early-stopping", type=int, default=50)
    ap.add_argument("--no-log-transform", action="store_true",
                    help="Wyłącza log1p transform targetu (domyślnie włączony)")
    ap.add_argument("--tune", action="store_true",
                    help="Bayesian hyperparameter search z Optuna (wymaga: pip install optuna)")
    ap.add_argument("--tune-trials", type=int, default=60)
    ap.add_argument("--stack", action="store_true",
                    help="Stacking z LightGBM (wymaga: pip install lightgbm)")
    ap.add_argument("--copy-to-backend", action="store_true",
                    help=f"Kopiuje wynik do {BACKEND_MODEL}")
    args = ap.parse_args()

    if not args.csv.exists():
        raise SystemExit(f"Brak {args.csv}. Najpierw uruchom scripts/extract_features.py.")

    df = pd.read_csv(args.csv)
    print(f"Wczytano {len(df)} wierszy z {args.csv}")
    if "weight_kg" not in df.columns or "pig_id" not in df.columns:
        raise SystemExit("CSV nie ma wymaganych kolumn: weight_kg, pig_id")
    missing = [c for c in FEATURE_ORDER if c not in df.columns]
    if missing:
        raise SystemExit(f"CSV nie ma kolumn cech: {missing}")

    X = df[FEATURE_ORDER].astype(np.float32).to_numpy()
    y = df["weight_kg"].astype(np.float32).to_numpy()
    groups = df["pig_id"].to_numpy()
    use_log = not args.no_log_transform

    print(f"Cechy: {len(FEATURE_ORDER)}  |  Log-transform: {use_log}")
    print(f"Zakres wag: {y.min():.1f} - {y.max():.1f} kg  "
          f"(mean={y.mean():.1f}, std={y.std():.1f})")
    print(f"Unikalne pig_id: {len(np.unique(groups))}")

    # ---- Hyperparameter tuning ----
    base_params = {
        "objective": "reg:squarederror",
        "eval_metric": "mae",
        "learning_rate": args.lr,
        "max_depth": args.max_depth,
        "subsample": 0.85,
        "colsample_bytree": 0.85,
        "min_child_weight": 4,
        "reg_lambda": 1.0,
        "reg_alpha": 0.01,
        "gamma": 0.0,
        "seed": args.seed,
        "verbosity": 1,
    }

    if args.tune:
        print("\n=== Bayesian Hyperparameter Search ===")
        best_hp = tune_hyperparams(
            X, y, groups,
            n_folds=args.n_folds, n_trials=args.tune_trials,
            use_log=use_log, seed=args.seed,
        )
        if best_hp:
            base_params.update({
                "learning_rate": best_hp.get("lr", args.lr),
                "max_depth": best_hp.get("max_depth", args.max_depth),
                "subsample": best_hp.get("subsample", 0.85),
                "colsample_bytree": best_hp.get("colsample_bytree", 0.85),
                "min_child_weight": best_hp.get("min_child_weight", 4),
                "reg_lambda": best_hp.get("reg_lambda", 1.0),
                "reg_alpha": best_hp.get("reg_alpha", 0.01),
                "gamma": best_hp.get("gamma", 0.0),
            })

    # ---- Cross-validation ----
    print(f"\n=== {args.n_folds}-Fold GroupKFold CV ===")
    fold_metrics, oof_pred, oof_mask = run_cv(
        X, y, groups, base_params,
        n_folds=args.n_folds, n_estimators=args.n_estimators,
        early_stopping=args.early_stopping, use_log=use_log,
    )

    cv_mae = float(np.mean([m["mae_kg"] for m in fold_metrics]))
    cv_mae_std = float(np.std([m["mae_kg"] for m in fold_metrics]))
    cv_rmse = float(np.mean([m["rmse_kg"] for m in fold_metrics]))
    cv_mape = float(np.mean([m["mape_pct"] for m in fold_metrics]))
    cv_r2 = float(np.mean([m["r2"] for m in fold_metrics]))

    print(f"\n=== CV Summary ===")
    print(f"MAE:  {cv_mae:.2f} ± {cv_mae_std:.2f} kg")
    print(f"RMSE: {cv_rmse:.2f} kg")
    print(f"MAPE: {cv_mape:.1f}%")
    print(f"R2:   {cv_r2:.3f}")

    # ---- Stacking ----
    if args.stack:
        print("\n=== Stacking z LightGBM ===")
        train_lightgbm_stack(X, y, groups, oof_pred, args.n_folds, args.seed)

    # ---- Train final model on all data (holdout from GroupShuffleSplit for monitoring) ----
    print("\n=== Training final model ===")
    splitter = GroupShuffleSplit(n_splits=1, test_size=0.1, random_state=args.seed)
    train_idx, val_idx = next(splitter.split(X, y, groups))

    booster, pred_final_val = train_single_xgb(
        X[train_idx], y[train_idx],
        X[val_idx], y[val_idx],
        base_params, args.n_estimators, args.early_stopping,
        use_log=use_log, verbose=True,
    )

    final_metrics = evaluate(y[val_idx], pred_final_val)
    print(f"\nFinal holdout: MAE={final_metrics['mae_kg']:.2f} kg  "
          f"RMSE={final_metrics['rmse_kg']:.2f} kg  R2={final_metrics['r2']:.3f}")

    # ---- Save ----
    args.out.mkdir(parents=True, exist_ok=True)
    model_path = args.out / "pig_weight.json"
    booster.save_model(str(model_path))

    metrics = {
        "cv_mae_kg": cv_mae,
        "cv_mae_std_kg": cv_mae_std,
        "cv_rmse_kg": cv_rmse,
        "cv_mape_pct": cv_mape,
        "cv_r2": cv_r2,
        "final_holdout": final_metrics,
        "n_samples": int(len(y)),
        "n_features": len(FEATURE_ORDER),
        "n_pig_ids": int(len(np.unique(groups))),
        "n_folds": args.n_folds,
        "use_log_transform": use_log,
        "tuned": args.tune,
        "params": base_params,
        "feature_order": FEATURE_ORDER,
        "fold_metrics": fold_metrics,
    }
    (args.out / "metrics.json").write_text(json.dumps(metrics, indent=2), encoding="utf-8")

    importance = booster.get_score(importance_type="gain")
    fi_rows = sorted(importance.items(), key=lambda kv: kv[1], reverse=True)
    fi_csv = "\n".join(["feature,gain", *[f"{k},{v:.4f}" for k, v in fi_rows]])
    (args.out / "feature_importance.csv").write_text(fi_csv, encoding="utf-8")

    # ---- Residuals plot ----
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt

        fig, axes = plt.subplots(1, 3, figsize=(16, 4.5))

        # OOF predictions
        oof_y = y[oof_mask]
        oof_p = oof_pred[oof_mask]
        residuals = oof_y - oof_p

        axes[0].scatter(oof_y, oof_p, s=8, alpha=0.5)
        lo = float(min(oof_y.min(), oof_p.min()))
        hi = float(max(oof_y.max(), oof_p.max()))
        axes[0].plot([lo, hi], [lo, hi], "r--", lw=1)
        axes[0].set_xlabel("rzeczywista (kg)")
        axes[0].set_ylabel("predykcja OOF (kg)")
        axes[0].set_title(f"OOF: MAE={cv_mae:.2f} kg  R2={cv_r2:.3f}")

        axes[1].scatter(oof_y, residuals, s=8, alpha=0.5)
        axes[1].axhline(0, color="r", lw=1, ls="--")
        axes[1].set_xlabel("rzeczywista (kg)")
        axes[1].set_ylabel("residuum (kg)")
        axes[1].set_title("Residua OOF")

        axes[2].hist(residuals, bins=40, edgecolor="white", alpha=0.7)
        axes[2].axvline(0, color="r", lw=1, ls="--")
        axes[2].set_xlabel("residuum (kg)")
        axes[2].set_ylabel("count")
        axes[2].set_title(f"Rozkład residuów (std={residuals.std():.2f} kg)")

        fig.tight_layout()
        fig.savefig(args.out / "residuals.png", dpi=150)
        plt.close(fig)

        # Feature importance plot
        fi_df = pd.DataFrame(fi_rows, columns=["feature", "gain"])
        fig2, ax2 = plt.subplots(figsize=(8, max(4, len(fi_df) * 0.25)))
        fi_top = fi_df.head(25)
        ax2.barh(fi_top["feature"][::-1], fi_top["gain"][::-1])
        ax2.set_xlabel("Gain")
        ax2.set_title("Top 25 Feature Importance")
        fig2.tight_layout()
        fig2.savefig(args.out / "feature_importance.png", dpi=150)
        plt.close(fig2)

        print(f"Wykresy: {args.out / 'residuals.png'}, {args.out / 'feature_importance.png'}")
    except ImportError:
        print("(matplotlib niezainstalowany — pomijam wykresy)")

    print(f"\nModel zapisany: {model_path}")
    print(f"Metryki:        {args.out / 'metrics.json'}")

    if args.copy_to_backend:
        BACKEND_MODEL.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(model_path, BACKEND_MODEL)
        print(f"Skopiowano do:  {BACKEND_MODEL}")
    else:
        print("(uruchom z --copy-to-backend, żeby skopiować do backend/models/)")


if __name__ == "__main__":
    main()
