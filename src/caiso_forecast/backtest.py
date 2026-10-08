"""Phase 6: walk-forward backtest. Expanding window: train on all target-days <= D-2 (complete at the origin),
forecast every hour of D. GBMs retrain every RETRAIN_DAYS; Chronos is zero-shot every day.

Usage: PYTHONPATH=src python -m caiso_forecast.backtest [--variant strict|lenient|observed] [--models gbm,chronos]
                                                          [--start YYYY-MM-DD] [--end YYYY-MM-DD] [--retrain 14]
Writes data/processed/forecasts_<variant>.parquet (long: model, target, ts_utc, origin, yhat, p10, p50, p90).
"""
from __future__ import annotations

import argparse
import logging
import time

import numpy as np
import pandas as pd
from . import config as C
from .features import feature_cols, TARGETS
from .models import GBM, Chronos

log = logging.getLogger("backtest")


def run(variant="strict", models=("gbm",), start=None, end=None, retrain_days=14, targets=TARGETS) -> pd.DataFrame:
    X = pd.read_parquet(C.PROCESSED / f"features_{variant}.parquet")
    X = X[X.date >= C.WEATHER_FULL_FROM].reset_index(drop=True)
    fc = feature_cols(X)
    start = pd.Timestamp(start or C.BACKTEST_FIRST_TARGET); end = pd.Timestamp(end or C.BACKTEST_LAST_TARGET)
    days = pd.date_range(start, end, freq="D")
    hist = pd.read_parquet(C.PROCESSED / "hourly.parquet").set_index("ts_utc")
    rows = []
    gbms: dict[str, GBM] = {}
    last_fit = None
    chronos = Chronos() if "chronos" in models else None
    t0 = time.time()
    for i, D in enumerate(days):
        origin = (D - pd.Timedelta(days=1)).tz_localize(C.TZ) + pd.Timedelta(hours=C.ORIGIN_HOUR_LOCAL)
        test = X[X.date == D]
        if test.empty:
            continue
        if "gbm" in models and (last_fit is None or (D - last_fit).days >= retrain_days):
            train = X[X.date <= D - pd.Timedelta(days=2)]
            for tgt in targets:
                gbms[tgt] = GBM(fc).fit(train, train[tgt])
            last_fit = D
            log.info("refit at %s on %d rows (%.0fs elapsed)", D.date(), len(train), time.time() - t0)
        for tgt in targets:
            if "gbm" in models:
                p = gbms[tgt].predict(test)
                for ts, r in zip(test.ts_utc, p.itertuples(index=False)):
                    rows.append(("gbm", tgt, ts, origin, r.yhat, r.p10, r.p50, r.p90))
            if chronos is not None:
                h = hist[tgt].loc[:origin - pd.Timedelta(hours=1)]       # last complete hour: D-1 08:00 local
                p = chronos.predict_day(h, horizon=int((test.ts_utc.max() - h.index[-1]) / pd.Timedelta(hours=1)))
                p = p.reindex(test.ts_utc)
                for ts, r in zip(test.ts_utc, p.itertuples(index=False)):
                    rows.append(("chronos", tgt, ts, origin, r.yhat, r.p10, r.p50, r.p90))
        if i % 50 == 0:
            log.info("day %d/%d %s", i, len(days), D.date())
    out = pd.DataFrame(rows, columns=["model", "target", "ts_utc", "origin", "yhat", "p10", "p50", "p90"])
    out["variant"] = variant
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--variant", default="strict"); ap.add_argument("--models", default="gbm")
    ap.add_argument("--start"); ap.add_argument("--end"); ap.add_argument("--retrain", type=int, default=14)
    ap.add_argument("--targets", default=",".join(TARGETS)); ap.add_argument("--out")
    a = ap.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
    out = run(a.variant, tuple(a.models.split(",")), a.start, a.end, a.retrain, a.targets.split(","))
    path = C.PROCESSED / (a.out or f"forecasts_{a.variant}_{a.models.replace(',', '+')}.parquet")
    out.to_parquet(path, index=False)
    print("wrote", path, out.shape)


if __name__ == "__main__":
    main()
