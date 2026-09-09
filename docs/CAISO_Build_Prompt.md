# Build Prompt — CAISO Day-Ahead Forecaster with a Live Track Record

Paste everything below into a coding assistant to start the build.

---

I'm building a **day-ahead electricity load & price forecasting project on live CAISO data**, and I want to learn and be able to defend every part — scaffold and explain with me layer by layer, don't hand me a finished black box. Leave the genuinely instructive parts (feature design, the backtest loop, the spike analysis, the battery replay logic) for me to implement with your guidance, and pause to check my understanding at each phase before moving on.

## The point of the project

This is not a tutorial project. It has five deliverables that most portfolio projects don't have, and they are the priority — the model itself is deliberately simple:

1. **A live, unfakeable track record.** A scheduled job publishes tomorrow's 24-hour forecast every afternoon *before* the day-ahead market outcome is known (committed to the repo with a timestamp), then grades it against actuals the next day. A public scoreboard page shows the running record. Forecasts issued in advance and graded honestly are the product.
2. **A real incumbent baseline.** I benchmark against **CAISO's own published day-ahead demand forecast** (via OASIS / `gridstatus`), not just seasonal-naive. For price, the honest framing is the DA–RT spread — the day-ahead LMP is already the market's forecast of real-time, so any edge claim must be against that.
3. **A dollarized decision layer.** A toy 4-hour battery does day-ahead arbitrage on my forecast, run blind through the walk-forward backtest: revenue on my forecast vs. the baselines vs. perfect foresight (the ceiling). Report "% of perfect-foresight value captured," and sweep risk tolerance into a small revenue/risk frontier. Accuracy metrics don't hire people; captured value does.
4. **A foundation-model challenger, judged honestly.** Enter a zero-shot time-series foundation model (TimesFM or Chronos) into the tournament against my GBM and the naive/incumbent baselines, same splits, same metrics. The verdict — wherever it lands, especially on spike hours — is a finding, not a footnote.
5. **Named-event post-mortems.** Two or three real, dated events from the data window (a heat wave, a low-wind evening ramp, a negative-price solar weekend): a one-page trader-desk post-mortem each — what the model said the day before, what happened hour by hour, where the P10–P90 band broke, what forward-looking signal would have caught it.

## Domain context (model this honestly)

Electricity can't be stored at grid scale, so CAISO runs a day-ahead market; it publishes hourly load, locational marginal prices (LMP), its own demand forecast, and wind/solar actuals + forecasts through OASIS. The structure that matters: the **duck curve** is a *net-load* (load minus renewables) phenomenon — solar suppresses midday prices, then the evening ramp hits as solar drops; prices are calm most hours then spike 10–50x on grid stress; seasonality is layered (hour × weekday × month × holiday × temperature) and **non-stationary** — the duck deepens every year as solar grows, so any fitted seasonal shape must be checked against trend.

## Build order

**Phase 0 — Repo.** Clean Python project (`src/`, `data/`, `notebooks/`, `forecasts/`, `README.md`). Libraries: `gridstatus`, `pandas`, LightGBM (point + quantile objectives), scikit-learn, matplotlib. Weather from Open-Meteo.

**Phase 1 — Data.** Pull 2+ years hourly for one CAISO zone/hub (SP15 or NP15): load, **CAISO's day-ahead load forecast**, day-ahead LMP, real-time LMP, wind + solar actuals and forecasts. Weather: use Open-Meteo's **historical *forecast* archive** (what the forecast said the day before), NOT observed actuals — using actuals-as-forecast is leakage and I want to quantify what honest weather inputs cost. Resolve timezones/DST carefully onto one tidy hourly index. Compute **net load** as a first-class column.

**Phase 2 — EDA.** Duck curve (price & net load by hour, split by year to show it deepening), temperature-vs-load U-shape, top ~1% price hours characterized (when, what weather, what net-load ramp). Identify the 2–3 candidate dates for the post-mortems now.

**Phase 3 — Baselines first.** (a) Seasonal-naive: same hour last week. (b) The incumbent: CAISO's own forecast. Score MAE/RMSE/MAPE overall AND split spike vs. normal hours. Every later claim is relative to these.

**Phase 4 — Leak-free features.** Calendar (hour, weekday, month, holiday), lags (t-24/48/168h), as-of rolling stats, day-ahead weather forecast for the target hour, solar/daylight proxy, net-load ramp features. I write a note per feature on why it's leak-free.

**Phase 5 — Models & tournament.** LightGBM point model for next-day 24 hourly values; quantile LightGBM for P10/P50/P90; the foundation-model challenger zero-shot. All compete on identical walk-forward splits.

**Phase 6 — Walk-forward backtest.** Expanding-window: train through day D, forecast D+1, roll forward across a year+. Metrics aggregated across origins, broken out by season and spike/normal. Output one scoreboard table: my model vs. TimesFM/Chronos vs. seasonal-naive vs. CAISO official.

**Phase 7 — Intervals & calibration.** P10–P90 coverage overall and by regime (spike vs. normal, ramp hours vs. midday), PIT histogram, pinball loss. Intervals should visibly widen on the evening ramp — show it.

**Phase 8 — Spike layer.** A classifier for P(price > threshold in tomorrow's evening ramp) from forecast weather + net-load features; report precision/recall and calibration, not just AUC. Then the failure analysis: quantify how much worse errors are on spike hours and why history-based models structurally miss them.

**Phase 9 — Battery replay.** Simple 4-hour battery, day-ahead arbitrage schedule optimized on each model's forecast, settled at actual prices, blind through the backtest. Perfect-foresight ceiling, % captured per model, and a risk-tolerance sweep → frontier plot.

**Phase 10 — Go live.** GitHub Action (or launchd) that daily: pulls latest data, retrains/updates, writes `forecasts/YYYY-MM-DD.json` before the operating day, grades yesterday's file, regenerates a static scoreboard page (GitHub Pages), and appends a grounded plain-English "grid briefing" generated ONLY from the model's actual outputs.

**Phase 11 — Packaging.** README leads with the live scoreboard link, the tournament table, one duck-curve-with-intervals figure, and the spike finding in one sentence — architecture below the fold. Add the post-mortems, a one-page model card (intended use, data window, known failure modes, calibration, misuse warnings), and a "design decisions & what I'd do differently" section.

## Hard rules

- Real data only; never synthesize the core series.
- Never let the model see the future: walk-forward everywhere, every feature as-of prediction time, historical *forecast* weather not observed weather.
- Every claim is vs. a named baseline, and CAISO's own forecast is the one that counts.
- Losses and misses get reported at full size — the honest verdict is the differentiator.
- Any LLM output is generated strictly from my model's numbers.
- At each phase, stop and quiz me on the reasoning before we move on.

Start with Phase 0 and Phase 1: scaffold the repo, then get one clean hourly dataframe pulled and verified (row counts, DST days, missing hours) before anything else.
