"""Project-wide constants. Everything that defines *what* data we model lives here."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
RAW = ROOT / "data" / "raw"
PROCESSED = ROOT / "data" / "processed"

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
WEATHER_VARS = ["temperature_2m", "apparent_temperature", "relative_humidity_2m", "dew_point_2m",
                "wind_speed_10m", "wind_gusts_10m", "cloud_cover", "shortwave_radiation",
                "direct_radiation", "precipitation"]
