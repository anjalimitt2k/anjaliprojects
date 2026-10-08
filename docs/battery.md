# Phase 9 — battery replay (1 MW / 4 MWh, 90% round-trip, 1 cycle/day), 2024-07-01 → 2026-09-06, 798 days

Schedule optimised on each entrant's day-ahead price forecast; settled at actual SP15 real-time hourly LMP. Perfect foresight = ceiling.

| entrant                 |   revenue $ |   $/MW-day |   % of perfect foresight |   losing days |   worst day $ |   p5 day $ |
|:------------------------|------------:|-----------:|-------------------------:|--------------:|--------------:|-----------:|
| perfect foresight       |      108504 |      136   |                    100   |             0 |           0.5 |       35   |
| DA LMP (market)         |       94337 |      118.2 |                     86.9 |            26 |         -46.5 |        8.5 |
| seasonal-naive RT (D-7) |       84563 |      106   |                     77.9 |            46 |         -81.5 |       -5.2 |
| Chronos-Bolt zero-shot  |       92919 |      116.4 |                     85.6 |            33 |         -56.5 |        7.2 |


Revenue by year ($):

|   date |   perfect foresight |   DA LMP (market) |   seasonal-naive RT (D-7) |   Chronos-Bolt zero-shot |
|-------:|--------------------:|------------------:|--------------------------:|-------------------------:|
|   2024 |               29587 |             26963 |                     24425 |                    26697 |
|   2025 |               49222 |             42657 |                     39014 |                    42006 |
|   2026 |               29695 |             24717 |                     21124 |                    24216 |


## Risk-tolerance sweep (trade only if the forecast's best-4-minus-worst-4 spread ≥ threshold)

| entrant                 |   min spread $/MWh |   days traded |   revenue $ |   p5 day $ |   std day $ |
|:------------------------|-------------------:|--------------:|------------:|-----------:|------------:|
| DA LMP (market)         |                  0 |           798 |       94337 |        8.5 |       129.6 |
| DA LMP (market)         |                  5 |           798 |       94337 |        8.5 |       129.6 |
| DA LMP (market)         |                 10 |           784 |       94213 |        6.5 |       129.7 |
| DA LMP (market)         |                 15 |           752 |       93364 |        0   |       130.3 |
| DA LMP (market)         |                 20 |           731 |       92814 |        0   |       130.8 |
| DA LMP (market)         |                 30 |           572 |       82953 |        0   |       137.3 |
| DA LMP (market)         |                 40 |           302 |       55343 |        0   |       137.1 |
| DA LMP (market)         |                 60 |            72 |       21361 |        0   |       125.6 |
| seasonal-naive RT (D-7) |                  0 |           798 |       84563 |       -5.2 |       112.9 |
| seasonal-naive RT (D-7) |                  5 |           796 |       84546 |       -4.6 |       112.9 |
| seasonal-naive RT (D-7) |                 10 |           788 |       84582 |       -0.1 |       112.8 |
| seasonal-naive RT (D-7) |                 15 |           767 |       82533 |        0   |       107.2 |
| seasonal-naive RT (D-7) |                 20 |           728 |       80519 |        0   |       108.4 |
| seasonal-naive RT (D-7) |                 30 |           550 |       65712 |        0   |       105.3 |
| seasonal-naive RT (D-7) |                 40 |           338 |       44578 |        0   |       103.8 |
| seasonal-naive RT (D-7) |                 60 |           113 |       16123 |        0   |        57.3 |
| Chronos-Bolt zero-shot  |                  0 |           798 |       92919 |        7.2 |       126   |
| Chronos-Bolt zero-shot  |                  5 |           797 |       92919 |        7.2 |       126   |
| Chronos-Bolt zero-shot  |                 10 |           789 |       92752 |        1.6 |       126.1 |
| Chronos-Bolt zero-shot  |                 15 |           767 |       91669 |        0   |       126.8 |
| Chronos-Bolt zero-shot  |                 20 |           715 |       89490 |        0   |       128.3 |
| Chronos-Bolt zero-shot  |                 30 |           497 |       71003 |        0   |       131.4 |
| Chronos-Bolt zero-shot  |                 40 |           243 |       41840 |        0   |       124.8 |
| Chronos-Bolt zero-shot  |                 60 |            66 |       12606 |        0   |        59.3 |