"""Phase 5: the contestants. All take the same feature matrix and return 24 hourly values (+ P10/P50/P90)."""
from __future__ import annotations

import numpy as np
import pandas as pd
from . import config as C

LGB_BASE = dict(n_estimators=600, learning_rate=0.04, num_leaves=31, min_child_samples=40, subsample=0.8,
                subsample_freq=1, colsample_bytree=0.8, reg_lambda=1.0, verbose=-1, n_jobs=4)
QUANTILES = (0.1, 0.5, 0.9)


class GBM:
    """LightGBM point model (L2) + three quantile models, one global model across hours."""

    def __init__(self, feature_cols: list[str]):
        self.fc = feature_cols
        self.point = None
        self.q = {}

    def fit(self, X: pd.DataFrame, y: pd.Series):
        import lightgbm as lgb  # lazy: LightGBM's libomp and torch's OpenMP crash when both load in one process
        m = y.notna()
        Xf, yf = X.loc[m, self.fc], y[m]
        self.point = lgb.LGBMRegressor(objective="regression", **LGB_BASE).fit(Xf, yf)
        for a in QUANTILES:
            self.q[a] = lgb.LGBMRegressor(objective="quantile", alpha=a, **LGB_BASE).fit(Xf, yf)
        return self

    def predict(self, X: pd.DataFrame) -> pd.DataFrame:
        out = pd.DataFrame(index=X.index)
        out["yhat"] = self.point.predict(X[self.fc])
        for a in QUANTILES:
            out[f"p{int(a*100)}"] = self.q[a].predict(X[self.fc])
        # enforce monotone quantiles
        out["p10"], out["p90"] = np.minimum(out.p10, out.p50), np.maximum(out.p90, out.p50)
        return out

    def importance(self) -> pd.Series:
        return pd.Series(self.point.feature_importances_, index=self.fc).sort_values(ascending=False)


class Chronos:
    """Zero-shot foundation model (amazon/chronos-bolt-small). Sees only the target's own history up to the
    origin (D-1 08:00), forecasts 40 steps, keeps the last 24 (= day D). No covariates, by design: that is the
    'does a general-purpose time-series model beat a domain GBM' question."""

    def __init__(self, model_id: str = "amazon/chronos-bolt-small", context_hours: int = 24 * 28):
        from chronos import BaseChronosPipeline
        import torch
        self.pipe = BaseChronosPipeline.from_pretrained(model_id, device_map="cpu", torch_dtype=torch.float32)
        self.ctx = context_hours

    def predict_day(self, history: pd.Series, horizon: int = 40) -> pd.DataFrame:
        """history: hourly target values ending at the last observed hour before the origin (UTC index)."""
        import torch
        h = history.dropna().iloc[-self.ctx:]
        qs, mean = self.pipe.predict_quantiles(torch.tensor(h.values, dtype=torch.float32),
                                               prediction_length=horizon, quantile_levels=[0.1, 0.5, 0.9])
        q = qs[0].numpy(); m = mean[0].numpy()
        idx = pd.date_range(h.index[-1] + pd.Timedelta(hours=1), periods=horizon, freq="h")
        return pd.DataFrame({"yhat": m, "p10": q[:, 0], "p50": q[:, 1], "p90": q[:, 2]}, index=idx)
