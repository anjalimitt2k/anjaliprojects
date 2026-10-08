# Design decisions & what I'd do differently

## Decisions, and the failure each one prevents

| decision | why | what it prevents |
|---|---|---|
| **Load actual = Today's Outlook demand**, not OASIS `SLD_FCST ACTUAL` | It is the quantity CAISO's forecast targets (MAPE 2.1 % vs 6.7 % against the other series) | Beating a strawman: a fake 7 % incumbent error, midday "wins" that are a basis artifact |
| **UTC hourly key; local time is a feature** | 23/25-hour days, three sources with three clock conventions | Fan-out joins, silently dropped or doubled hours, lag-24 features off by one after every transition |
| **Origin fixed at 09:00 D-1**, CAISO's own DA load forecast excluded as a feature | Ten minutes before CAISO publishes; being a post-processor of the incumbent isn't a forecast | Claiming an "edge" that is CAISO's forecast plus noise |
| **Strict weather = run ≥ 24 h (hours 00–09) / ≥ 48 h (10–23) before valid time** | `previous_day1` for a 20:00 target is a run initialised at 20:00 D-1, after the origin | Up to 14 h of weather-model updates leaking into the evening ramp, the hours that matter most |
| **Three weather variants run through the same backtest** | The prompt asks what honest weather inputs cost; a number beats an assertion | Hand-waving about leakage |
| **Net load = demand − fleet solar − wind from the same feed family; CAISO's own net demand carried alongside** | CAISO's published net demand subtracts ~8.5 % less solar than any solar series it publishes | A 2 GW midday bias nobody can explain, discovered when someone compares to CAISO's chart |
| **Backtest from 2024-07-01, not 2025** | 2025 had zero severe DA price hours; the market calmed sharply after the battery build-out | A spike layer with no positives, and a tournament judged on one calm year |
| **Retrain every 14 days, expanding window** | 57 refits × 12 LightGBM fits is an hour; daily refits buy nothing measurable | A backtest too slow to iterate on |
| **Chronos in its own process** | Homebrew libomp (LightGBM) and torch's OpenMP segfault together on macOS | Silent exit-139 crashes mid-backtest |
| **Multi-hour Outlook outages left NaN** (18 h), only isolated single hours interpolated | Training or scoring on invented load is worse than a missing row | Invisible imputation bias |
| **Briefing generated from the forecast file's numbers by a template** | "Any LLM output is generated strictly from my model's numbers"; a template cannot hallucinate | A briefing that quotes a heat wave the model didn't forecast |

## What I'd do differently

1. **Price target.** Forecasting hourly RT LMP at 24–39 h lead is mostly forecasting the DA LMP plus a skewed residual. A
   cleaner product is a *two-stage* model: DA LMP (bid-relevant) and the DA→RT spread sign/size for the evening ramp. The
   battery replay would then schedule on DA and hedge on the spread.
2. **Spike definition.** A fixed full-window p95 of DA LMP (≈$71) is honest but the market moved under it: by 2025 the same
   dollar level is rarer, so the label base rate drifts. A rolling-quantile or regime-conditioned label would keep the
   classifier's positives meaningful across years.
3. **Weather.** Six Open-Meteo points is cheap and defensible, but a population-weighted composite from the actual
   forecast ensemble (and ERA5 only for diagnostics) would give the model a proper "state of California" input instead of
   six correlated series that LightGBM has to average itself.
4. **Non-stationarity.** `trend_days` lets trees split by era but cannot extrapolate the deepening duck. A better fix is to
   model *net load* and add renewables capacity as an exogenous level, or to detrend the midday hours explicitly.
5. **Chronos with covariates.** The zero-shot entrant sees only the target's own history, by design. Chronos-2 and TimesFM
   accept covariates; a fair second round would give them the same forecast weather and renewables inputs.
6. **Live-vs-backtest weather lead.** The live job uses the current Open-Meteo forecast at ~09:15 D-1 (10–35 h lead),
   slightly fresher than the strict training features (24–48 h). It is documented, directionally favourable, and the
   graded record will show whether it matters; the strictly consistent alternative is to wait for `previous_day2` to exist,
   which it never does for a future hour.
7. **Grading lag.** Real-time prices are final after settlement; we grade next day on the published 15-min FMM prices, which
   can be revised. A re-grade after T+5 days would be the audit-grade version.
