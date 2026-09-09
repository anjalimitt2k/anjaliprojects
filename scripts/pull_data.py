"""Phase 1 entry point: pull + cache raw sources, build the tidy hourly frame, save it.

Usage:  python scripts/pull_data.py                 # all sources, then build
        python scripts/pull_data.py lmp_da weather  # only these sources, no build
"""
import logging, sys
sys.path.insert(0, "src")
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
for noisy in ["gridstatus", "urllib3", "requests"]:
    logging.getLogger(noisy).setLevel(logging.ERROR)
from caiso_forecast import data
only = sys.argv[1:] or None
raw = data.pull_all(only)
if only:
    sys.exit(0)
df = data.build_hourly(raw)
data.save_hourly(df)
print(f"hourly.parquet: {df.shape[0]} rows x {df.shape[1]} cols, {df.ts_utc.min()} -> {df.ts_utc.max()}")
