# Tournament scoreboard — walk-forward 2024-07-01 → 2026-09-06

Identical rows, identical splits for every entrant. Spike/severe = hours whose actual DA LMP ≥ p95 / p99 of the full window. Weather features: strict variant (no run newer than the 09:00 D-1 origin).


## target `load_mw` — MAE (MW), n=19143 hours

| split            |   CAISO official DA forecast |   Chronos-Bolt zero-shot |   LightGBM (ours) |   seasonal-naive (D-7) |
|:-----------------|-----------------------------:|-------------------------:|------------------:|-----------------------:|
| all              |                        512.1 |                   1202.1 |             728.9 |                 1891.6 |
| regime=normal    |                        504.5 |                   1183.7 |             712   |                 1863   |
| spike+severe     |                        884.5 |                   2109.7 |            1557.5 |                 3298.1 |
| regime=severe    |                       1413.5 |                   3237.3 |            3065.3 |                 5190.9 |
| ramp hours 17-21 |                        566.6 |                   1580.9 |             843.6 |                 2366.3 |


RMSE / bias / MAPE, all hours:

| model                      |    RMSE |   bias |   MAPE |
|:---------------------------|--------:|-------:|-------:|
| Chronos-Bolt zero-shot     | 1814.79 |   3.7  |   4.82 |
| LightGBM (ours)            | 1066.21 | -28.59 |   2.93 |
| CAISO official DA forecast |  719.17 | 106.96 |   2.1  |
| seasonal-naive (D-7)       | 2830.5  |  20.22 |   7.51 |


By season (MAE):

| split         |   CAISO official DA forecast |   Chronos-Bolt zero-shot |   LightGBM (ours) |   seasonal-naive (D-7) |
|:--------------|-----------------------------:|-------------------------:|------------------:|-----------------------:|
| season=autumn |                        414.5 |                    896.8 |             579.2 |                 1520.6 |
| season=spring |                        462   |                   1195.7 |             565.5 |                 1534.5 |
| season=summer |                        621.1 |                   1592.2 |             913.9 |                 2676.9 |
| season=winter |                        440.6 |                    740.6 |             677   |                 1148.6 |


By year (MAE):

|   year |   CAISO official DA forecast |   Chronos-Bolt zero-shot |   LightGBM (ours) |   seasonal-naive (D-7) |
|-------:|-----------------------------:|-------------------------:|------------------:|-----------------------:|
|   2024 |                        588.8 |                   1381.5 |            1048.7 |                 2362.7 |
|   2025 |                        475.6 |                   1079.8 |             631.6 |                 1622.2 |
|   2026 |                        509   |                   1249.3 |             635.8 |                 1939.4 |

## target `lmp_rt` — MAE ($/MWh), n=19152 hours

| split            |   Chronos-Bolt zero-shot |   DA LMP (market) |   LightGBM (ours) |   seasonal-naive RT (D-7) |
|:-----------------|-------------------------:|------------------:|------------------:|--------------------------:|
| all              |                      9.8 |               7.2 |               9.9 |                      14.2 |
| regime=normal    |                      9   |               6.3 |               9   |                      13.2 |
| spike+severe     |                     48.6 |              48.3 |              57   |                      62.5 |
| regime=severe    |                    105.5 |             147.2 |             112.4 |                     112.8 |
| ramp hours 17-21 |                     12.8 |              10.8 |              14.5 |                      18.7 |


RMSE / bias, all hours:

| model                   |   RMSE |   bias |
|:------------------------|-------:|-------:|
| Chronos-Bolt zero-shot  |  22.21 |  -1.52 |
| LightGBM (ours)         |  23.35 |   1.11 |
| DA LMP (market)         |  19.58 |   1.56 |
| seasonal-naive RT (D-7) |  31.13 |   0.03 |


By season (MAE):

| split         |   Chronos-Bolt zero-shot |   DA LMP (market) |   LightGBM (ours) |   seasonal-naive RT (D-7) |
|:--------------|-------------------------:|------------------:|------------------:|--------------------------:|
| season=autumn |                      9.1 |               6.7 |               7.6 |                      11.7 |
| season=spring |                      9.9 |               6.6 |               8.5 |                      13.7 |
| season=summer |                     10.5 |               8.2 |              11.9 |                      16.3 |
| season=winter |                      9   |               6.4 |               9.5 |                      12.9 |

## target `lmp_da` — MAE ($/MWh), n=19152 hours

| split            |   Chronos-Bolt zero-shot |   LightGBM (ours) |   naive DA (D-2) |   seasonal-naive DA (D-7) |
|:-----------------|-------------------------:|------------------:|-----------------:|--------------------------:|
| all              |                      6.8 |               5.1 |              8.7 |                      10.7 |
| regime=normal    |                      6.2 |               4.6 |              8.1 |                       9.9 |
| spike+severe     |                     36.5 |              32.4 |             39.1 |                      49.1 |
| regime=severe    |                    128.8 |             108.3 |            114.2 |                     149.6 |
| ramp hours 17-21 |                      9.3 |               7.2 |             10.8 |                      14.4 |


RMSE / bias, all hours:

| model                   |   RMSE |   bias |
|:------------------------|-------:|-------:|
| Chronos-Bolt zero-shot  |  13.2  |  -0.91 |
| LightGBM (ours)         |  10.97 |  -0.15 |
| naive DA (D-2)          |  16.27 |  -0.03 |
| seasonal-naive DA (D-7) |  19.88 |  -0    |


By season (MAE):

| split         |   Chronos-Bolt zero-shot |   LightGBM (ours) |   naive DA (D-2) |   seasonal-naive DA (D-7) |
|:--------------|-------------------------:|------------------:|-----------------:|--------------------------:|
| season=autumn |                      6.2 |               4.2 |              8.4 |                       9   |
| season=spring |                      6.6 |               4.6 |              8.6 |                       9.7 |
| season=summer |                      7.4 |               5.7 |              9.2 |                      12.2 |
| season=winter |                      6.2 |               5.3 |              7.9 |                      10.2 |


## Weather-input ablation (LightGBM, load)

strict = honest (no run after the origin); lenient = previous_day1 for all hours (up to 14 h fresher than allowed); observed = ERA5 (leakage ceiling).

| weather variant   |   MAE |   RMSE |   bias |   MAPE |   MAE spike+severe |
|:------------------|------:|-------:|-------:|-------:|-------------------:|
| strict            | 729.4 | 1067.2 |  -29.3 |    2.9 |             1571.4 |
| lenient           | 713   | 1041   |  -10.5 |    2.9 |             1558.8 |
| observed          | 670.3 |  973.7 |  -42.9 |    2.7 |             1646.5 |