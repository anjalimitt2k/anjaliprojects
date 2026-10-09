# Phase 8 — spike layer

Label: any hour 17–21 on D with RT hourly LMP ≥ $71/MWh (the full-window p95 of DA LMP). Severe: ≥ $118. Features: evening means of the strict day-ahead feature set (forecast weather, CAISO renewables forecast, net-load proxy, recent price state). Walk-forward, retrained every 28 days.


## Evening-spike classifier, 2024-07-01 → 2026-09-06: 798 days, 98 positives (12.3 %)

- AUC 0.881, average precision 0.566 (base rate 0.123), Brier 0.0799 (climatology Brier 0.1077)

Precision / recall by decision threshold:

|   threshold |   flagged days |   precision |   recall |   F1 |
|------------:|---------------:|------------:|---------:|-----:|
|         0.2 |            114 |        0.53 |     0.61 | 0.57 |
|         0.3 |            104 |        0.55 |     0.58 | 0.56 |
|         0.4 |             97 |        0.57 |     0.56 | 0.56 |
|         0.5 |             87 |        0.62 |     0.55 | 0.58 |
|         0.6 |             76 |        0.66 |     0.51 | 0.57 |


Reliability (predicted vs observed rate by bin):

| p             |   n |   mean_p |   obs_rate |
|:--------------|----:|---------:|-----------:|
| (-0.001, 0.1] | 660 |    0.006 |      0.047 |
| (0.1, 0.2]    |  24 |    0.13  |      0.292 |
| (0.2, 0.3]    |  10 |    0.24  |      0.3   |
| (0.3, 0.4]    |   7 |    0.345 |      0.286 |
| (0.4, 0.5]    |  10 |    0.454 |      0.1   |
| (0.5, 0.7]    |  21 |    0.603 |      0.476 |
| (0.7, 1.0]    |  66 |    0.879 |      0.667 |


Positives by year (the regime shift):

|   date |   days |   positives |   mean_p |
|-------:|-------:|------------:|---------:|
|   2024 |    184 |          47 |    0.218 |
|   2025 |    365 |          26 |    0.065 |
|   2026 |    249 |          25 |    0.095 |


Top features (split gain count):

|                                |   importance |
|:-------------------------------|-------------:|
| lmp_da_d1_samehour_evmean      |          134 |
| wind_speed_10m_fres_evmean     |          121 |
| temperature_2m_sd_evmean       |          116 |
| wind_speed_10m_la_evmean       |          115 |
| wind_fc_mw_evmean              |          106 |
| caiso_err_d2_samehour_evmean   |          103 |
| doy_sin_evmean                 |           95 |
| lmp_rt_d1_early_max_evmean     |           94 |
| relative_humidity_2m_sj_evmean |           94 |
| trend_days_evmean              |           92 |
| relative_humidity_2m_sd_evmean |           85 |
| lmp_rt_lag48_evmean            |           84 |


Severe label (≥ $118): 23 positives; AUC 0.936, AP 0.288.


## Failure analysis: how much worse on spike hours, and why

| target   | model                      |   MAE normal |   MAE spike+severe |   MAE severe |   × worse (severe/normal) |   bias severe |
|:---------|:---------------------------|-------------:|-------------------:|-------------:|--------------------------:|--------------:|
| load_mw  | LightGBM (ours)            |        712.3 |             1571.4 |       3095.2 |                       4.3 |       -2644.4 |
| load_mw  | Chronos-Bolt zero-shot     |       1184   |             2131   |       3302.4 |                       2.8 |       -3032.8 |
| load_mw  | CAISO official DA forecast |        505   |              888   |       1418   |                       2.8 |        1296.2 |
| lmp_rt   | LightGBM (ours)            |          9   |               57   |        112.4 |                      12.6 |         -51.8 |
| lmp_rt   | Chronos-Bolt zero-shot     |          9   |               48.6 |        105.5 |                      11.8 |         -80.7 |
| lmp_rt   | DA LMP (market)            |          6.3 |               48.3 |        147.2 |                      23.2 |          50.1 |


The ten highest RT hours and what each forecast said the day before:

| ts_local                  |   lmp_rt |   lmp_da |   gbm__lmp_rt |   gbm__lmp_rt__p90 |   chronos__lmp_rt |
|:--------------------------|---------:|---------:|--------------:|-------------------:|------------------:|
| 2024-07-23 19:00:00-07:00 |      908 |      276 |           117 |                105 |               100 |
| 2024-07-24 19:00:00-07:00 |      845 |      205 |           142 |                130 |               100 |
| 2024-07-09 19:00:00-07:00 |      644 |      246 |            87 |                 86 |                90 |
| 2024-07-10 19:00:00-07:00 |      446 |      411 |            88 |                 85 |                90 |
| 2024-07-23 20:00:00-07:00 |      440 |      124 |            75 |                 95 |                79 |
| 2024-07-08 19:00:00-07:00 |      401 |      133 |            77 |                 80 |                67 |
| 2024-07-25 19:00:00-07:00 |      384 |      224 |           137 |                130 |               174 |
| 2024-07-11 19:00:00-07:00 |      256 |      532 |            90 |                 88 |               115 |
| 2024-10-07 18:00:00-07:00 |      184 |      156 |            96 |                115 |                74 |
| 2026-08-26 19:00:00-07:00 |      182 |      150 |            85 |                115 |                79 |


**Why history-based models structurally miss spikes.** Every lag feature (D-2, D-7, 7-day mean) describes a calm market because spikes are rare and short; the training loss (L2 / pinball) is dominated by the ~95 % of normal hours, so the fitted function is pulled toward the conditional *median*, which is calm. Spikes are driven by variables that are either absent (outages, gas price, import availability) or only weakly proxied by forecast weather and net-load ramp. The bias column shows it: every model under-forecasts severe hours by a large negative bias; the RT target is right-skewed and the models are not.