# Phase 1 data notes — what each series is and what bit us

## Sources (all via `gridstatus` 0.36 unless noted)

| column(s) | source | granularity | notes |
|---|---|---|---|
| `load_mw` | CAISO Today's Outlook `demand.csv` ("Current demand") | 5-min → hourly mean | **This** is the series CAISO's forecast targets. Fall-back days are missing the second 01:00 hour at source (CSV has 288 rows, not 300); we interpolate that one hour and set `load_imputed=True`. |
| `load_fc_caiso_mw`, `load_fc_publish_utc` | OASIS `SLD_FCST` market_run_id=DAM, TAC area `CA ISO-TAC` | hourly | The incumbent. Published ~09:10 local the day before. Publish time is kept so the "was it really day-ahead" claim is checkable. |
| `lmp_da*` | OASIS `PRC_LMP` DAM, node `TH_SP15_GEN-APND` | hourly | Energy / congestion / loss components kept. |
| `lmp_rt`, `lmp_rt_max15`, `lmp_rt_min15` | OASIS `PRC_RTPD_LMP` (15-min FMM), same node | 15-min → hourly mean | Max/min within hour retained for spike work. |
| `solar_sys_mw`, `wind_sys_mw`, `*_zone_*` | OASIS `SLD_REN_FCST` ACTUAL, locations CAISO + SP15 | hourly | Night solar is slightly negative (station load). Fine. |
| `solar_fc_sys_mw`, `wind_fc_sys_mw`, `*_fc_zone_*` | OASIS `SLD_REN_FCST` DAM | hourly | Published ~07:00 local the day before. |
| `<var>_<point>` (10 vars × 6 points) | Open-Meteo **previous-runs** API, `<var>_previous_day1`, `best_match` | hourly, UTC | The value the model run one day earlier predicted for that hour. Not observed weather. |
| `net_load_mw` | derived | | `load - solar_sys - wind_sys`. The duck curve lives here. |
| `net_load_fc_caiso_mw` | derived | | Same, from CAISO's own DA load + DA renewables forecasts — the incumbent's net-load view. |

## Zone decision
Price is SP15 (trading hub). Load and net load are CAISO-system because OASIS publishes load by TAC area, not by pricing zone; SP15-only renewables are kept as `*_zone_*` columns. The duck curve and the evening ramp are system phenomena, so system net load is the right driver for a hub price.

## The trap we caught in Phase 1 (would have poisoned Phase 3 and everything after)
`gridstatus.CAISO().get_load_hourly()` returns OASIS `SLD_FCST` with market_run_id=ACTUAL. For `CA ISO-TAC` that series runs **up to ~6.5 GW (20%+) above** the Outlook demand in midday hours and ~1 GW above overnight, with a solar-shaped bulge. Every CAISO forecast run (7DA, 2DA, DAM, and even the 15-min RTPD forecast published minutes ahead) agrees with the Outlook demand, not with `SLD_FCST ACTUAL`. Scoring CAISO's forecast against that series gives a bogus ~7% MAPE and a fake midday "miss" that our model would then "beat". Against the Outlook demand, CAISO's DA MAPE is ~1.6%, matching what it publishes. We use the Outlook demand as the actual. The validator checks for this shape of mismatch explicitly.

## Timezone / DST handling
* All joins are on a UTC hourly key. Every source is converted to UTC and floored to the hour *before* aggregation; local clock fields are derived afterwards.
* Spring-forward days (23 local hours) have no local 02:00 row; fall-back days (25) have two local 01:00 rows distinguished by offset. The validator derives the transition dates from the tz database rather than a hard-coded list.
* Open-Meteo is requested in UTC precisely to avoid its ambiguous-local-hour behaviour.

## SSL
The machine's network injects a self-signed CA; `truststore.inject_into_ssl()` is called before any HTTPS. OASIS is plain HTTP and unaffected.
