# Phase 1 validation — hourly.parquet

Window (local): 2023-07-01 → 2026-09-06  | zone SP15, hub TH_SP15_GEN-APND

## Index integrity
- [PASS] row count 27936 == expected 27936 hours
- [PASS] ts_utc strictly increasing, no duplicates
- [PASS] every step is exactly 1h (unique diffs: [Timedelta('0 days 01:00:00')])

## DST transition days (local clock)
- [PASS] spring-forward 2024-03-10: 23 rows (expect 23)
- [PASS] spring-forward 2025-03-09: 23 rows (expect 23)
- [PASS] spring-forward 2026-03-08: 23 rows (expect 23)
- [PASS] fall-back 2023-11-05: 25 rows (expect 25)
- [PASS] fall-back 2024-11-03: 25 rows (expect 25)
- [PASS] fall-back 2025-11-02: 25 rows (expect 25)
- [PASS] all other days have 24 rows (offenders: {})
- [PASS] no local 02:00 rows on spring-forward days
- [PASS] exactly two local 01:00 rows on each fall-back day (6 found)

## Missing hours per core column
- load_mw: 18 missing (0.06%)
- [PASS] load_mw missing < 0.5% (0.06%)
- load_fc_caiso_mw: 0 missing (0.00%)
- [PASS] load_fc_caiso_mw missing < 0.5% (0.00%)
- lmp_da: 0 missing (0.00%)
- [PASS] lmp_da missing < 0.5% (0.00%)
- lmp_rt: 0 missing (0.00%)
- [PASS] lmp_rt missing < 0.5% (0.00%)
- solar_outlook_mw: 18 missing (0.06%)
- [PASS] solar_outlook_mw missing < 0.5% (0.06%)
- wind_outlook_mw: 18 missing (0.06%)
- [PASS] wind_outlook_mw missing < 0.5% (0.06%)
- solar_sys_mw: 61 missing (0.22%)
- [PASS] solar_sys_mw missing < 0.5% (0.22%)
- wind_sys_mw: 62 missing (0.22%)
- [PASS] wind_sys_mw missing < 0.5% (0.22%)
- solar_fc_sys_mw: 0 missing (0.00%)
- [PASS] solar_fc_sys_mw missing < 0.5% (0.00%)
- wind_fc_sys_mw: 0 missing (0.00%)
- [PASS] wind_fc_sys_mw missing < 0.5% (0.00%)
- net_load_mw: 18 missing (0.06%)
- [PASS] net_load_mw missing < 0.5% (0.06%)
- temperature_2m_la: 0 missing (0.00%) (from 2024-01-20)
- [PASS] temperature_2m_la missing < 0.5% (0.00%) (from 2024-01-20)
- shortwave_radiation_fres: 0 missing (0.00%) (from 2024-01-20)
- [PASS] shortwave_radiation_fres missing < 0.5% (0.00%) (from 2024-01-20)
- pre-2024-01-20 rows: 4873; temperature coverage 89.9%, radiation coverage 0.4% (archive limitation, documented)
- load_mw unfilled gap hours: 18 on dates ['2024-01-11', '2024-06-27', '2024-08-29', '2024-09-24']
- load_mw imputed rows: 3 → ['2023-11-05', '2024-11-03', '2025-11-02']
- [PASS] load imputation only on fall-back days (the Outlook feed drops that hour at source)
- [PASS] exactly one imputed load hour per fall-back day (3 vs 3)
- load_mw: longest NaN run 9h
- [PASS] load_mw longest NaN run <= 24h (9)
- load_fc_caiso_mw: longest NaN run 0h
- [PASS] load_fc_caiso_mw longest NaN run <= 24h (0)
- lmp_da: longest NaN run 0h
- [PASS] lmp_da longest NaN run <= 24h (0)
- lmp_rt: longest NaN run 0h
- [PASS] lmp_rt longest NaN run <= 24h (0)
- solar_outlook_mw: longest NaN run 9h
- [PASS] solar_outlook_mw longest NaN run <= 24h (9)
- wind_outlook_mw: longest NaN run 9h
- [PASS] wind_outlook_mw longest NaN run <= 24h (9)
- solar_sys_mw: longest NaN run 5h
- [PASS] solar_sys_mw longest NaN run <= 24h (5)
- wind_sys_mw: longest NaN run 5h
- [PASS] wind_sys_mw longest NaN run <= 24h (5)
- solar_fc_sys_mw: longest NaN run 0h
- [PASS] solar_fc_sys_mw longest NaN run <= 24h (0)
- wind_fc_sys_mw: longest NaN run 0h
- [PASS] wind_fc_sys_mw longest NaN run <= 24h (0)
- net_load_mw: longest NaN run 9h
- [PASS] net_load_mw longest NaN run <= 24h (9)
- temperature_2m_la: longest NaN run 0h
- [PASS] temperature_2m_la longest NaN run <= 24h (0)
- shortwave_radiation_fres: longest NaN run 0h
- [PASS] shortwave_radiation_fres longest NaN run <= 24h (0)

## Sanity ranges
- [PASS] load in [9, 55] GW (min 11021, max 47325; ~11 GW spring-Sunday-midday lows are real BTM-solar records)
- [PASS] fleet solar peaks > 10 GW (max 23780)
- [PASS] night solar ~0: 0 hours with |solar| > 500 MW at 00-03h (|max| 338; small negatives are station load)
- [PASS] DA LMP in [-200, 3000] (min -67.1, max 1247.6)
- [PASS] RT LMP in [-500, 3000] (min -85.4, max 1982.5)
- [PASS] LA temperature in [-5, 50] C (min 3.3, max 40.9)
- [PASS] no over-full hours (>4 RT intervals or >12 5-min intervals)

## Cross-source consistency (catches wrong-series / misaligned joins)
- CAISO official DA load forecast MAPE vs actual: 2.11%  (published ~1.5–3%; a solar-shaped 7%+ gap means the wrong actual series)
- [PASS] CAISO DA forecast MAPE < 4%
- worst hour-of-day APE: h12 = 3.53%
- [PASS] no hour-of-day with CAISO APE > 6% (midday bulge = BTM-solar series mismatch)
- corr(DA LMP, RT LMP) = 0.790
- [PASS] DA/RT LMP correlation > 0.5 (misaligned hours would destroy this)
- [PASS] DA/RT correlation at lag 0 (0.790) beats lag 1 (0.744) → hours aligned
- corr(fleet solar, Fresno day-before shortwave fc) at shift -1/0/+1h: 0.886 / 0.923 / 0.875
- [PASS] solar vs forecast radiation peaks at lag 0 (>0.9) → weather hour-aligned after preceding-hour shift
- [PASS] Outlook fleet solar vs OASIS solar actual correlation 0.999 > 0.98 (same timing, different scope)
- OASIS solar / Outlook solar energy ratio = 0.833 (OASIS scope is narrower; document, don't 'fix')
- [PASS] mean fleet solar peaks at local hour 11 (expect 10–14; the fleet plateaus 10–14)
- [PASS] duck-curve belly: mean net load minimum at local hour 12 (expect 10–15)
- [PASS] summer load peaks at local hour 18 (expect 16–20)
- [PASS] LA temperature peaks at local hour 14 (expect 13–17)
- CAISO DA forecast publish lead: min 14.8h, median 26.8h
- [PASS] every CAISO DA forecast was published >= 12h before the target hour (it is truly day-ahead)

## Summary stats
|                          |   count |    mean |     min |     50% |     max |
|:-------------------------|--------:|--------:|--------:|--------:|--------:|
| load_mw                  |   27918 | 24426.4 | 11020.8 | 23636.4 | 47325.4 |
| load_fc_caiso_mw         |   27936 | 24536.5 | 11227.5 | 23686.6 | 48519.6 |
| lmp_da                   |   27936 |    34.6 |   -67.1 |    36.1 |  1247.6 |
| lmp_rt                   |   27936 |    32.8 |   -85.4 |    33.7 |  1982.5 |
| solar_outlook_mw         |   27918 |  6235.1 |   -82.4 |   598.8 | 23780.4 |
| wind_outlook_mw          |   27918 |  2599.6 |    40.5 |  2408.1 |  8253.5 |
| solar_sys_mw             |   27875 |  5202.1 |  -352.2 |   445.7 | 19738.5 |
| wind_sys_mw              |   27874 |  1767.9 |   -28.6 |  1569.5 |  5956.8 |
| solar_fc_sys_mw          |   27936 |  5863.3 |     0   |   603.1 | 20591.1 |
| wind_fc_sys_mw           |   27936 |  1814.1 |    24.8 |  1626.3 |  5894.2 |
| net_load_mw              |   27918 | 15591.6 | -8852.2 | 18037.5 | 41917.3 |
| temperature_2m_la        |   27444 |    18.3 |     3.3 |    17.6 |    40.9 |
| shortwave_radiation_fres |   23084 |   237.6 |     0   |     0   |  1055   |

**0 FAIL / 58 PASS**