# Model card — CAISO day-ahead load & SP15 price forecaster

**Version:** walk-forward evaluation 2024-07-01 → 2026-09-06; live since 2026-10-09. **Code:** `src/caiso_forecast/`.

## Intended use
Research/portfolio forecaster producing, at 09:00 Pacific on D-1, hourly forecasts for day D of (a) CAISO system load, (b) SP15
real-time hourly LMP, (c) SP15 day-ahead LMP, each with P10/P50/P90 bands, plus a daily probability of an evening (17–21) real-time
price spike. It exists to be **graded against CAISO's own day-ahead load forecast and against the day-ahead LMP**, in public, every day.
It is not a bidding system and is not calibrated for any financial decision beyond the toy 1 MW battery replay in `docs/battery.md`.

## Data
- Window 2023-07-01 → present; full-feature window from **2024-01-20** (earlier rows lack forecast weather beyond temperature).
- Actuals: CAISO Today's Outlook 5-min demand and fuel mix (hourly means); OASIS 15-min FMM RT LMP (hourly mean/max/min); OASIS DA LMP.
- Incumbent: OASIS `SLD_FCST` DAM for `CA ISO-TAC`, publish time retained (median lead 26.8 h, minimum 14.8 h).
- Weather: Open-Meteo previous-runs API, `best_match`, six California points; **strict rule** = run ≥ 24 h before valid time for
  hours 00–09 of D, ≥ 48 h for 10–23, so no run post-dates the origin. Radiation/precipitation shifted to interval-start convention.
- Known data limitations: 18 hours of CAISO Outlook outages left NaN; OASIS renewables actual has ~0.2 % hour dropouts; CAISO's published
  net demand subtracts ~8.5 % less solar than any solar series it publishes (we carry both; see `docs/data_notes.md`).

## Models
- **LightGBM**, one global model per target (hour-of-day is a feature), L2 objective for the point forecast and three quantile
  objectives (0.1/0.5/0.9); 92 features (`docs/features.md`); expanding window, retrained every 14 days in the backtest, daily when live.
- **Conformal bands**: P10/P90 replaced by P50 ± per-hour-of-day empirical residual quantiles from the previous 60 graded days.
  The raw quantile bands are badly under-dispersed (56 % coverage at nominal 80 %); conformal brings them to 76 %.
- **Chronos-Bolt-small** zero-shot (no covariates) as the foundation-model challenger. Runs in a separate process (OpenMP clash with LightGBM).
- **Spike classifier**: LightGBM, day-level, evening means of the same feature set, retrained every 28 days.

## Performance (walk-forward, identical rows for all entrants; `docs/scoreboard.md`)
| target | ours | incumbent | naive | Chronos |
|---|---|---|---|---|
| Load MAE (MW), all hours | **729** (2.9 % MAPE) | CAISO **512** (2.1 %) | 1,892 | 1,202 |
| Load MAE, severe-price hours | 3,065 | 1,414 | 5,191 | 3,237 |
| RT LMP MAE ($/MWh), all | 9.9 | DA LMP **7.2** | 14.2 | 9.8 |
| RT LMP MAE, severe hours | 112 | 147 | 113 | **106** |
| DA LMP MAE ($/MWh) | **5.1** | — | 8.7 | 6.8 |
| Battery: % of perfect-foresight value | 83.8 % | DA LMP 86.9 % | 77.9 % | 85.6 % |

**The honest verdict:** we beat every naive baseline and the zero-shot foundation model on load and DA price, and we do **not** beat
CAISO on load (42 % higher MAE overall, 2.2× on severe hours) nor the DA LMP on real-time price. The foundation model is better
calibrated out of the box (81 % coverage) and wins the severe-hour RT price split; it loses on everything else.

## Calibration (`docs/calibration.md`)
Conformal P10–P90: 76 % coverage on load and RT price (PIT 11/37/39/13 and 11/40/37/12). Coverage on spike/severe hours: 72 % (load),
**46 % (RT price)** — the bands are honest on calm days and too narrow exactly when it matters.

## Known failure modes
1. **Cannot extrapolate.** Trees flatten at the training maximum: 6.6 GW low at the 47.3 GW record (`docs/postmortems/2024-09-05.md`).
2. **Structurally calm on price.** Every history-based entrant under-forecasts severe RT hours by $50–80 of bias; the spike
   classifier (AUC 0.88, AP 0.57 vs 0.12 base rate) is the only component that reacts, and it is over-confident above p=0.7 (observed 0.67).
3. **Early-window weakness.** 2024 MAE 1,049 MW with five months of training; 2025–26 ~635 MW. The record improves as the window grows.
4. **Regime drift.** Spike labels at a fixed $71 threshold: 47 positives in H2-2024, 26 in all of 2025, 25 in 2026 — the base rate moved.
5. **Live vs backtest weather lead.** Live uses the current forecast at ~09:15 D-1 (10–35 h lead), fresher than the strict training
   features; expected to help slightly, visible in the graded record if it does.

## Misuse warnings
- Do not trade on the point price forecast: it is a conditional median of a right-skewed target and will miss every spike.
- Do not read the battery revenue as attainable: 1 MW toy, no degradation, no bid/ask, settled at hourly means not 5-min prices.
- Do not compare the live record to the backtest without noting the retrain cadence and weather-lead differences above.
- The briefing text is a template over the forecast file's numbers; it contains no information the model did not produce.
