# Phase 3 — baselines (backtest window 2024-07-01 → 2026-09-06)

Spike thresholds (DA LMP, full window): spike ≥ $71.2/MWh, severe ≥ $117.6/MWh.


## target `load_mw`

MAE by split:

| split            |   CAISO official DA forecast |   naive (D-2) |   seasonal-naive (D-7) |
|:-----------------|-----------------------------:|--------------:|-----------------------:|
| all              |                        512.7 |        2045.8 |                 1891.6 |
| ramp hours 17-21 |                        567.8 |        2028.4 |                 2366.3 |
| regime=normal    |                        505   |        2040.7 |                 1863   |
| regime=severe    |                       1418   |        2793.3 |                 5190.9 |
| spike+severe     |                        888   |        2296.3 |                 3298.1 |


All metrics, split = all:

| model                      |     n |     MAE |    RMSE |   bias |   MAPE |
|:---------------------------|------:|--------:|--------:|-------:|-------:|
| CAISO official DA forecast | 19146 |  512.68 |  720.21 | 107.76 |   2.1  |
| seasonal-naive (D-7)       | 19137 | 1891.56 | 2830.5  |  20.22 |   7.51 |
| naive (D-2)                | 19140 | 2045.82 | 2787.18 |   4.26 |   8.61 |


By season (MAE):

| split         |   CAISO official DA forecast |   naive (D-2) |   seasonal-naive (D-7) |
|:--------------|-----------------------------:|--------------:|-----------------------:|
| season=autumn |                        415.5 |        1730   |                 1520.6 |
| season=spring |                        462   |        2023.3 |                 1534.5 |
| season=summer |                        622.2 |        2440.3 |                 2676.9 |
| season=winter |                        440.6 |        1600.4 |                 1148.6 |

## target `lmp_rt`

MAE by split:

| split            |   DA LMP (market's forecast) |   seasonal-naive RT (D-7) |
|:-----------------|-----------------------------:|--------------------------:|
| all              |                          7.2 |                      14.2 |
| ramp hours 17-21 |                         10.8 |                      18.7 |
| regime=normal    |                          6.3 |                      13.2 |
| regime=severe    |                        147.2 |                     112.8 |
| spike+severe     |                         48.3 |                      62.5 |


All metrics, split = all:

| model                      |     n |   MAE |   RMSE |   bias |
|:---------------------------|------:|------:|-------:|-------:|
| DA LMP (market's forecast) | 19152 |  7.17 |  19.58 |   1.56 |
| seasonal-naive RT (D-7)    | 19152 | 14.23 |  31.13 |   0.03 |


By season (MAE):

| split         |   DA LMP (market's forecast) |   seasonal-naive RT (D-7) |
|:--------------|-----------------------------:|--------------------------:|
| season=autumn |                          6.7 |                      11.7 |
| season=spring |                          6.6 |                      13.7 |
| season=summer |                          8.2 |                      16.3 |
| season=winter |                          6.4 |                      12.9 |

## target `lmp_da`

MAE by split:

| split            |   naive DA (D-2) |   seasonal-naive DA (D-7) |
|:-----------------|-----------------:|--------------------------:|
| all              |              8.7 |                      10.7 |
| ramp hours 17-21 |             10.8 |                      14.4 |
| regime=normal    |              8.1 |                       9.9 |
| regime=severe    |            114.2 |                     149.6 |
| spike+severe     |             39.1 |                      49.1 |


All metrics, split = all:

| model                   |     n |   MAE |   RMSE |   bias |
|:------------------------|------:|------:|-------:|-------:|
| seasonal-naive DA (D-7) | 19152 | 10.69 |  19.88 |  -0    |
| naive DA (D-2)          | 19152 |  8.67 |  16.27 |  -0.03 |


By season (MAE):

| split         |   naive DA (D-2) |   seasonal-naive DA (D-7) |
|:--------------|-----------------:|--------------------------:|
| season=autumn |              8.4 |                       9   |
| season=spring |              8.6 |                       9.7 |
| season=summer |              9.2 |                      12.2 |
| season=winter |              7.9 |                      10.2 |