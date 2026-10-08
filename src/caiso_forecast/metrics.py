"""Shared scoring. Every model in the tournament is scored by exactly this code on exactly these splits."""
from __future__ import annotations

import numpy as np
import pandas as pd
from . import config as C

SEASON = {12: "winter", 1: "winter", 2: "winter", 3: "spring", 4: "spring", 5: "spring",
          6: "summer", 7: "summer", 8: "summer", 9: "summer", 10: "autumn", 11: "autumn"}


def spike_thresholds(df: pd.DataFrame) -> dict[str, float]:
    """Fixed $/MWh thresholds from the full-window DA LMP distribution (a definition, not a model)."""
    return {k: float(df.lmp_da.quantile(q)) for k, q in C.SPIKE_Q.items()}


def add_regimes(df: pd.DataFrame, thr: dict[str, float]) -> pd.DataFrame:
    df = df.copy()
    df["regime"] = np.where(df.lmp_da >= thr["severe"], "severe", np.where(df.lmp_da >= thr["spike"], "spike", "normal"))
    df["season"] = df.month_local.map(SEASON)
    df["ramp"] = df.hour_local.between(17, 21)
    return df


def score(y: pd.Series, yhat: pd.Series, mape: bool = True) -> dict[str, float]:
    m = y.notna() & yhat.notna()
    y, yhat = y[m], yhat[m]
    e = yhat - y
    out = {"n": int(m.sum()), "MAE": float(e.abs().mean()), "RMSE": float(np.sqrt((e ** 2).mean())), "bias": float(e.mean())}
    if mape:
        out["MAPE"] = float((e.abs() / y.abs()).mean() * 100)
    return out


def score_table(df: pd.DataFrame, target: str, models: dict[str, str], mape: bool) -> pd.DataFrame:
    """df must carry `regime`, `season`, `ramp`. models: name -> column of predictions."""
    rows = []
    splits = {"all": pd.Series(True, index=df.index)}
    for r in ["normal", "spike", "severe"]:
        splits[f"regime={r}"] = df.regime == r
    splits["spike+severe"] = df.regime != "normal"
    for s in ["winter", "spring", "summer", "autumn"]:
        splits[f"season={s}"] = df.season == s
    splits["ramp hours 17-21"] = df.ramp
    for name, col in models.items():
        for sname, mask in splits.items():
            sc = score(df.loc[mask, target], df.loc[mask, col], mape)
            rows.append({"model": name, "split": sname, **sc})
    return pd.DataFrame(rows)
