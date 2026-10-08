"""Chronos must run in a process without LightGBM loaded (OpenMP runtime clash). Prints one JSON line."""
import json, sys
import pandas as pd
from . import config as C
from .models import Chronos
from .features import TARGETS

D = pd.Timestamp(sys.argv[1])
df = pd.read_parquet(C.PROCESSED / "hourly_live.parquet").set_index("ts_utc")
origin = (D - pd.Timedelta(days=1)).tz_localize(C.TZ) + pd.Timedelta(hours=C.ORIGIN_HOUR_LOCAL)
lo = D.tz_localize(C.TZ).tz_convert("UTC"); hi = (D + pd.Timedelta(days=1)).tz_localize(C.TZ).tz_convert("UTC") - pd.Timedelta(hours=1)
want = pd.date_range(lo, hi, freq="h")
ch = Chronos(); out = {}
for tgt in TARGETS:
    h = df[tgt].loc[:origin - pd.Timedelta(hours=1)].dropna()
    p = ch.predict_day(h, horizon=int((want[-1] - h.index[-1]) / pd.Timedelta(hours=1))).reindex(want)
    out[tgt] = {k: [round(float(v), 2) for v in p[k]] for k in ["yhat", "p10", "p50", "p90"]}
print(json.dumps(out))
