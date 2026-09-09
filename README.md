# CAISO Day-Ahead Forecaster — with a live, graded track record

> Status: **Phase 1 (data) complete — 58/58 validation checks pass** (`data/processed/validation_report.md`). Nothing below the data layer exists yet, on purpose.

A day-ahead load & price forecaster for CAISO (SP15 hub, system load) whose product is not the model but the
**record**: every afternoon a job commits tomorrow's 24-hour forecast before the day-ahead outcome is known, grades
it the next day, and publishes the running scoreboard. Every claim is measured against **CAISO's own published
day-ahead forecast**, not just seasonal-naive.

Deliverables (in priority order): live scoreboard → incumbent benchmark → dollarized battery replay →
foundation-model challenger judged honestly → named-event post-mortems. See `docs/CAISO_Build_Prompt.md`.

## Layout
```
src/caiso_forecast/   config.py  data.py (pull + tidy join)  validate.py (Phase 1 gate)
scripts/              pull_data.py
data/raw/             per-source parquet cache (gitignored)
data/processed/       hourly.parquet + validation_report.md
docs/                 build prompt, data_notes.md (what each series is, and the traps)
forecasts/            YYYY-MM-DD.json, committed before each operating day (Phase 10)
```

## Reproduce Phase 1
```
uv venv -p 3.12 && uv pip install -e ".[dev]"     # needs `brew install libomp` on macOS
.venv/bin/python scripts/pull_data.py              # ~40 min first time, cached after
PYTHONPATH=src .venv/bin/python -m caiso_forecast.validate
```
