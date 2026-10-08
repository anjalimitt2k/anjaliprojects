# Phase 4 — features and why each one is leak-free

**Origin:** 09:00 local on D-1 (ten minutes before CAISO publishes its DA load forecast). A feature is admissible only if its
value is fixed by that instant. Three facts do most of the work: (1) day D-2 is complete; (2) only hours 00–08 of D-1 are
complete; (3) CAISO's DA *renewables* forecast for D is out at ~07:00 D-1, but its DA *load* forecast is out at ~09:10 —
**deliberately excluded** as a feature, otherwise the model is a post-processor of the incumbent it claims to beat.

| feature(s) | why it's available at 09:00 D-1 |
|---|---|
| `hour_local`, `dow_local`, `month_local`, `is_weekend`, `is_holiday`, `doy_sin/cos`, `hour_sin/cos`, `is_dst`, `daylight_h` | Calendar / astronomy; known for any date. |
| `trend_days` | Days since 2023-07-01. Lets trees split by era so the deepening duck isn't averaged across years. Cannot extrapolate — a documented limitation of GBMs. |
| `<target>_lag48/168/336` | Same hour on D-2, D-7, D-14 (UTC-exact shifts). D-2 is the most recent complete day. *Not* D-1: hours 09–23 of D-1 don't exist yet. |
| `net_load_lag48/168` | Same construction on net load. |
| `load_d1_early_mean`, `load_d1_h8`, `lmp_rt_d1_early_*` | Aggregates of D-1 hours 00–08 only — the last observed values before the origin. |
| `load_h_mean7`, `lmp_rt_h_mean7`, `net_load_h_mean7` | Mean at the target hour over D-8..D-2 (rolling 7, shifted by 2 days). |
| `load_daymax_d2`, `load_daymax_mean7`, `lmp_rt_daymax_d2`, `lmp_rt_daymax_max7` | Daily extremes of complete days only. |
| `caiso_fc_d1_samehour` | CAISO's DA forecast *for D-1*, published 09:10 on D-2. Known. (Its forecast for D is not.) |
| `caiso_err_d2_samehour` | CAISO's realised error on D-2 = actual D-2 − forecast published D-3. Both known. |
| `lmp_da_d1_samehour` | The DA LMP for D-1, published ~13:00 on D-2. Known. (DA LMP for D clears ~13:00 D-1 — excluded.) |
| `solar_fc_mw`, `wind_fc_mw`, `solar_fc_ramp3`, `solar_fc_daymax` | CAISO's DA renewables forecast for D, published ~07:00 D-1 (`Publish Time` kept in the raw data proves it). |
| `net_load_proxy`, `net_load_proxy_ramp3` | `load_lag168 − solar_fc − wind_fc`: last week's load shape with tomorrow's renewables. Both terms admissible. |
| `<var>_<point>` (7 weather vars × 6 points) | Open-Meteo previous-runs: **strict** variant uses the run ≥ 24 h before valid time for hours 00–09 and ≥ 48 h for 10–23, so every run predates the origin. |
| `temp_mean6`, `temp_socal`, `cdh_socal`, `temp_daymax/min`, `sw_fres_ramp3` | Derived from the same forecast fields. |
| `temp_daymax_d1` | Yesterday's forecast daily max (heat persistence). From the D-1 run set. |

Radiation and precipitation were shifted −1 h in the loader so that, like every CAISO column, the value at `ts` describes
the interval *starting* at `ts`.

## The three weather variants (ablation, Phase 6)
- **strict** — the headline. Honest to the minute.
- **lenient** — `previous_day1` for all hours. Up to 14 h of model updates the operator wouldn't have. Prices freshness.
- **observed** — ERA5. Pure leakage; the ceiling. The gap strict→observed is "what honest weather inputs cost".
