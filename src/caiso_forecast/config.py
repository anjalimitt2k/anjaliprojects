"""Project-wide constants. Everything that defines *what* data we model lives here."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
RAW = ROOT / "data" / "raw"
PROCESSED = ROOT / "data" / "processed"
for _d in (RAW, PROCESSED):          # gitignored, so they don't exist on a fresh checkout (CI)
    _d.mkdir(parents=True, exist_ok=True)

TZ = "US/Pacific"                  # CAISO operating timezone (local clock, observes DST)
ZONE = "SP15"                      # price zone; load/net-load are CAISO-system (there is no SP15 load series)
HUB = "TH_SP15_GEN-APND"           # SP15 trading-hub pricing node on OASIS
LOAD_AREA = "CA ISO-TAC"           # system-total TAC area in SLD_FCST

START = "2023-07-01"               # window start (inclusive, local date)
END = "2026-09-06"                 # window end (inclusive, local date); leave 2 days for RT settlement lag

# Open-Meteo previous-runs API: `<var>_previous_day1` = the value the model run *one day earlier*
# predicted for that hour. This is the honest "what the forecast said yesterday" input.
WEATHER_POINTS = {                 # population/load centres; SoCal inland drives SP15 peak
    "la":   (34.05, -118.24),
    "riv":  (33.95, -117.40),
    "sd":   (32.72, -117.16),
    "fres": (36.74, -119.79),
    "sac":  (38.58, -121.49),
    "sj":   (37.34, -121.89),
}
# Open-Meteo's previous-runs archive (every model) carries only temperature before this date, and nothing
# at all 2023-12-30..2024-01-19. Weather-driven models train from here; earlier rows serve baselines + EDA.
WEATHER_FULL_FROM = "2024-01-20"
WEATHER_VARS = ["temperature_2m", "apparent_temperature", "relative_humidity_2m", "dew_point_2m",
                "wind_speed_10m", "wind_gusts_10m", "cloud_cover", "shortwave_radiation",
                "direct_radiation", "precipitation"]

# ---------------------------------------------------------------- Phase 2+ decisions (locked 2026-10-08)
# Forecast origin: 09:00 local on D-1, ten minutes before CAISO publishes its DA forecast (~09:10).
# Every feature must be computable from data available at this instant.
ORIGIN_HOUR_LOCAL = 9
# Walk-forward window: train from WEATHER_FULL_FROM; first forecast origin -> last operating day.
BACKTEST_FIRST_TARGET = "2024-07-01"   # includes the Sep-2024 heat wave; 2025 had zero severe DA hours
BACKTEST_LAST_TARGET = END
# Spike definition (set from EDA quantiles of DA LMP over the full window; see docs/eda.md):
SPIKE_Q = {"spike": 0.95, "severe": 0.99}
