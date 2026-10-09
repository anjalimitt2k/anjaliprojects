# Phase 9 — battery replay (1 MW / 4 MWh, 90% round-trip, 1 cycle/day), 2024-07-01 → 2026-09-06, 798 days

Schedule optimised on each entrant's day-ahead price forecast; settled at actual SP15 real-time hourly LMP. Perfect foresight = ceiling.

| entrant                 |   revenue $ |   $/MW-day |   % of perfect foresight |   losing days |   worst day $ |   p5 day $ |
|:------------------------|------------:|-----------:|-------------------------:|--------------:|--------------:|-----------:|
| perfect foresight       |      108504 |      136   |                    100   |             0 |           0.5 |       35   |
| DA LMP (market)         |       94337 |      118.2 |                     86.9 |            26 |         -46.5 |        8.5 |
| seasonal-naive RT (D-7) |       84563 |      106   |                     77.9 |            46 |         -81.5 |       -5.2 |
| LightGBM (ours)         |       90947 |      114   |                     83.8 |            30 |         -46.7 |        5.6 |
| Chronos-Bolt zero-shot  |       92919 |      116.4 |                     85.6 |            33 |         -56.5 |        7.2 |


Revenue by year ($):

|   date |   perfect foresight |   DA LMP (market) |   seasonal-naive RT (D-7) |   LightGBM (ours) |   Chronos-Bolt zero-shot |
|-------:|--------------------:|------------------:|--------------------------:|------------------:|-------------------------:|
|   2024 |               29587 |             26963 |                     24425 |             24753 |                    26697 |
|   2025 |               49222 |             42657 |                     39014 |             42635 |                    42006 |
|   2026 |               29695 |             24717 |                     21124 |             23558 |                    24216 |


## Risk-tolerance sweep (trade only if the forecast's best-4-minus-worst-4 spread ≥ threshold τ)

| entrant                 |   min spread $/MWh |   days traded |   revenue $ |   losses on losing days $ |   losing days |   std day $ |
|:------------------------|-------------------:|--------------:|------------:|--------------------------:|--------------:|------------:|
| DA LMP (market)         |                  0 |           798 |       94337 |                    -344.2 |            26 |       129.6 |
| DA LMP (market)         |                  5 |           798 |       94337 |                    -344.2 |            26 |       129.6 |
| DA LMP (market)         |                 10 |           784 |       94213 |                    -265.3 |            21 |       129.7 |
| DA LMP (market)         |                 15 |           752 |       93364 |                    -167.4 |            12 |       130.3 |
| DA LMP (market)         |                 20 |           731 |       92814 |                    -127.9 |             9 |       130.8 |
| DA LMP (market)         |                 30 |           572 |       82953 |                     -49.5 |             6 |       137.3 |
| DA LMP (market)         |                 40 |           302 |       55343 |                      -7.1 |             1 |       137.1 |
| DA LMP (market)         |                 60 |            72 |       21361 |                      -7.1 |             1 |       125.6 |
| seasonal-naive RT (D-7) |                  0 |           798 |       84563 |                   -1105.9 |            46 |       112.9 |
| seasonal-naive RT (D-7) |                  5 |           796 |       84546 |                   -1085.3 |            45 |       112.9 |
| seasonal-naive RT (D-7) |                 10 |           788 |       84582 |                    -948.9 |            40 |       112.8 |
| seasonal-naive RT (D-7) |                 15 |           767 |       82533 |                    -889   |            37 |       107.2 |
| seasonal-naive RT (D-7) |                 20 |           728 |       80519 |                    -697.2 |            28 |       108.4 |
| seasonal-naive RT (D-7) |                 30 |           550 |       65712 |                    -442.1 |            19 |       105.3 |
| seasonal-naive RT (D-7) |                 40 |           338 |       44578 |                    -187.3 |             8 |       103.8 |
| seasonal-naive RT (D-7) |                 60 |           113 |       16123 |                     -13.9 |             1 |        57.3 |
| LightGBM (ours)         |                  0 |           798 |       90947 |                    -438   |            30 |       113   |
| LightGBM (ours)         |                  5 |           798 |       90947 |                    -438   |            30 |       113   |
| LightGBM (ours)         |                 10 |           787 |       90813 |                    -387   |            24 |       113.1 |
| LightGBM (ours)         |                 15 |           768 |       90377 |                    -326   |            21 |       113.4 |
| LightGBM (ours)         |                 20 |           732 |       88991 |                    -269.5 |            16 |       114.6 |
| LightGBM (ours)         |                 30 |           591 |       78624 |                    -202.9 |            12 |       114.9 |
| LightGBM (ours)         |                 40 |           355 |       55780 |                    -135.4 |             6 |       119.8 |
| LightGBM (ours)         |                 60 |           119 |       21469 |                     -69.4 |             2 |        73.3 |
| Chronos-Bolt zero-shot  |                  0 |           798 |       92919 |                    -582.7 |            33 |       126   |
| Chronos-Bolt zero-shot  |                  5 |           797 |       92919 |                    -582.7 |            33 |       126   |
| Chronos-Bolt zero-shot  |                 10 |           789 |       92752 |                    -533.5 |            30 |       126.1 |
| Chronos-Bolt zero-shot  |                 15 |           767 |       91669 |                    -467.3 |            25 |       126.8 |
| Chronos-Bolt zero-shot  |                 20 |           715 |       89490 |                    -312   |            15 |       128.3 |
| Chronos-Bolt zero-shot  |                 30 |           497 |       71003 |                    -201.7 |             8 |       131.4 |
| Chronos-Bolt zero-shot  |                 40 |           243 |       41840 |                     -37.4 |             2 |       124.8 |
| Chronos-Bolt zero-shot  |                 60 |            66 |       12606 |                       0   |             0 |        59.3 |