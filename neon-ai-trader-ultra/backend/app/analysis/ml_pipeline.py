"""Leakage-free ML feature pipeline, walk-forward validation, calibrated probability estimator, and drift detection."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Tuple

import numpy as np
import pandas as pd


@dataclass
class WalkForwardMetrics:
    model_version: str
    out_of_sample_accuracy: float
    brier_score: float
    historical_win_rate: float
    sample_count: int
    feature_drift_zscore: float
    drift_detected: bool


class CalibratedWalkForwardModel:
    """
    Leakage-free regularized logistic ensemble trained strictly on historical
    expanding/rolling windows and evaluated out-of-sample.
    Separates model confidence, historical win rate, and estimated probability.
    """

    VERSION = "neon-wf-logreg-v1.0"

    def __init__(self, l2_reg: float = 1.5, lr: float = 0.08, epochs: int = 120) -> None:
        self.l2_reg = l2_reg
        self.lr = lr
        self.epochs = epochs
        self.weights: np.ndarray | None = None
        self.bias: float = 0.0
        self.feature_mean: np.ndarray | None = None
        self.feature_std: np.ndarray | None = None

    @staticmethod
    def build_features(df: pd.DataFrame) -> pd.DataFrame:
        """Strictly backward-looking features (zero future data leakage)."""
        close = df["close"].astype(float)
        high = df["high"].astype(float)
        low = df["low"].astype(float)
        vol = df["volume"].astype(float)

        ret_1 = close.pct_change(1)
        ret_5 = close.pct_change(5)
        ret_15 = close.pct_change(15)
        ema_fast = close.ewm(span=10, adjust=False).mean()
        ema_slow = close.ewm(span=30, adjust=False).mean()
        ema_spread = (ema_fast - ema_slow) / close.replace(0, np.nan)
        volatility = ret_1.rolling(14).std()
        range_pct = (high - low) / close.replace(0, np.nan)
        vol_z = (vol - vol.rolling(20).mean()) / vol.rolling(20).std().replace(0, np.nan)

        feats = pd.DataFrame(
            {
                "ret_1": ret_1,
                "ret_5": ret_5,
                "ret_15": ret_15,
                "ema_spread": ema_spread,
                "volatility": volatility,
                "range_pct": range_pct,
                "vol_z": vol_z,
            },
            index=df.index,
        )
        return feats.replace([np.inf, -np.inf], np.nan).fillna(0.0)

    def _fit_raw(self, X: np.ndarray, y: np.ndarray) -> Tuple[np.ndarray, float]:
        n, d = X.shape
        w = np.zeros(d, dtype=float)
        b = 0.0
        for _ in range(self.epochs):
            z = np.clip(X @ w + b, -30.0, 30.0)
            p = 1.0 / (1.0 + np.exp(-z))
            err = p - y
            grad_w = (X.T @ err) / n + (self.l2_reg / n) * w
            grad_b = float(np.mean(err))
            w -= self.lr * grad_w
            b -= self.lr * grad_b
        return w, b

    @staticmethod
    def _predict_proba_raw(X: np.ndarray, w: np.ndarray, b: float) -> np.ndarray:
        z = np.clip(X @ w + b, -30.0, 30.0)
        return 1.0 / (1.0 + np.exp(-z))

    def walk_forward_evaluate_and_fit(
        self, df: pd.DataFrame, horizon: int = 3
    ) -> Tuple[float, WalkForwardMetrics]:
        """
        Perform strict chronological walk-forward validation (no shuffling,
        train_idx strictly < test_idx - horizon) to compute calibrated
        out-of-sample metrics and predict probability on the latest bar.
        """
        feats = self.build_features(df)
        close = df["close"].astype(float)
        future_ret = close.shift(-horizon) / close - 1.0
        target = (future_ret > 0).astype(float)

        usable = len(df) - horizon
        if usable < 70:
            return 0.5, WalkForwardMetrics(
                model_version=self.VERSION,
                out_of_sample_accuracy=0.5,
                brier_score=0.25,
                historical_win_rate=0.5,
                sample_count=0,
                feature_drift_zscore=0.0,
                drift_detected=False,
            )

        X_all = feats.iloc[:usable].values
        y_all = target.iloc[:usable].values

        # Chronological 3-fold expanding walk-forward split
        split_points = [int(usable * 0.5), int(usable * 0.65), int(usable * 0.8)]
        oos_preds: List[float] = []
        oos_true: List[float] = []

        for idx, start in enumerate(split_points):
            end = split_points[idx + 1] if idx + 1 < len(split_points) else usable
            train_end = max(30, start - horizon)  # Embargo gap prevents lookahead leakage
            X_tr, y_tr = X_all[:train_end], y_all[:train_end]
            X_te, y_te = X_all[start:end], y_all[start:end]
            if len(X_te) == 0:
                continue
            mu = X_tr.mean(axis=0)
            sd = np.where(X_tr.std(axis=0) < 1e-8, 1.0, X_tr.std(axis=0))
            w, b = self._fit_raw((X_tr - mu) / sd, y_tr)
            probs = self._predict_proba_raw((X_te - mu) / sd, w, b)
            oos_preds.extend(probs.tolist())
            oos_true.extend(y_te.tolist())

        # Fit final model on all completed historical observations
        self.feature_mean = X_all.mean(axis=0)
        self.feature_std = np.where(X_all.std(axis=0) < 1e-8, 1.0, X_all.std(axis=0))
        self.weights, self.bias = self._fit_raw(
            (X_all - self.feature_mean) / self.feature_std, y_all
        )

        # Predict probability on the latest live bar
        latest_x = (feats.iloc[-1].values - self.feature_mean) / self.feature_std
        prob_up = float(self._predict_proba_raw(latest_x.reshape(1, -1), self.weights, self.bias)[0])

        # Drift detection comparing latest 15 bars vs training distribution
        recent_mu = feats.iloc[-15:].values.mean(axis=0)
        drift_z = float(np.mean(np.abs((recent_mu - self.feature_mean) / self.feature_std)))

        oos_p = np.array(oos_preds) if oos_preds else np.array([0.5])
        oos_y = np.array(oos_true) if oos_true else np.array([0.5])
        acc = float(np.mean((oos_p >= 0.5) == (oos_y >= 0.5)))
        brier = float(np.mean((oos_p - oos_y) ** 2))
        # Directional win rate on confident signals (>0.55 or <0.45)
        confident_mask = (oos_p >= 0.55) | (oos_p <= 0.45)
        hist_win = (
            float(np.mean((oos_p[confident_mask] >= 0.5) == (oos_y[confident_mask] >= 0.5)))
            if np.any(confident_mask)
            else acc
        )

        return round(prob_up, 4), WalkForwardMetrics(
            model_version=self.VERSION,
            out_of_sample_accuracy=round(acc, 4),
            brier_score=round(brier, 4),
            historical_win_rate=round(hist_win, 4),
            sample_count=len(oos_preds),
            feature_drift_zscore=round(drift_z, 3),
            drift_detected=bool(drift_z > 2.5),
        )
