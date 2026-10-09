"""Phase 10: go live. One daily run (09:00–12:00 Pacific on D-1, before the DA market closes at 10:00 — we aim
for 09:xx so the origin matches the backtest):

  1. update_data(D-1)     : pull the tail of every source (actuals through D-2 complete, D-1 partial)
  2. forecast(D)          : train GBMs on every complete day, forecast D's 24 hours (+ Chronos zero-shot),
                            write forecasts/D.json with the issue timestamp — the unfakeable record
  3. grade(D-1)           : score yesterday's file against actuals and CAISO's official forecast -> track_record.csv
  4. render_site()        : regenerate site/index.html (scoreboard + running record) and the grid briefing

Usage: PYTHONPATH=src python -m caiso_forecast.live [--target YYYY-MM-DD] [--skip-update] [--no-chronos]
"""
from __future__ import annotations

import argparse
import json
import logging
import subprocess
import sys
from datetime import datetime, timezone

import numpy as np
import pandas as pd
from . import config as C, data, metrics as M
from .features import build as build_features, feature_cols, TARGETS
from .models import GBM

log = logging.getLogger("live")
FORECASTS = C.ROOT / "forecasts"
TRACK = C.ROOT / "data" / "live" / "track_record.csv"
SITE = C.ROOT / "site"


def today_local() -> pd.Timestamp:
    return pd.Timestamp.now(tz=C.TZ).normalize()


# ------------------------------------------------------------------ 1. data
def update_data(through: pd.Timestamp) -> pd.DataFrame:
    """through = D-1 (today, partial). Actual-type sources through today (partial day is fine, missing is fine);
    day-ahead products (renewables DA forecast, CAISO DA load forecast, DA LMP) through D = tomorrow."""
    D = through + pd.Timedelta(days=1)
    data.update_sources(through.strftime("%Y-%m-%d"), names=["load_5min", "fuel_mix_5min", "net_demand_5min", "load_sld_actual",
                                                             "lmp_rt15", "ren_hourly", "weather", "weather_d2"])
    data.update_sources(D.strftime("%Y-%m-%d"), names=["ren_fc_dam", "load_fc_da", "lmp_da"])
    return rebuild_hourly(D)


def rebuild_hourly(end_local: pd.Timestamp) -> pd.DataFrame:
    saved = C.END
    try:
        C.END = end_local.strftime("%Y-%m-%d")
        raw = {k: pd.read_parquet(C.RAW / f"{k}.parquet") for k in data.SOURCES if (C.RAW / f"{k}.parquet").exists()}
        df = data.build_hourly(raw)
    finally:
        C.END = saved
    return df


# ------------------------------------------------------------------ 2. forecast
def forecast(D: pd.Timestamp, df: pd.DataFrame, use_chronos: bool = True) -> dict:
    """D = target local date. Trains on complete days (<= D-2), predicts D. Never re-issues: an existing file is the record."""
    FORECASTS.mkdir(exist_ok=True)
    existing = FORECASTS / f"{D.strftime('%Y-%m-%d')}.json"
    if existing.exists():
        log.info("forecast for %s already issued at %s; not overwriting", D.date(), json.loads(existing.read_text())["issued_at_utc"])
        return json.loads(existing.read_text())
    issued = datetime.now(timezone.utc)
    # slot the current weather forecast for D into the weather columns of D's rows (both d1 and d2 slots, so
    # the strict rule sees the same, fresher-than-training forecast; documented in the model card)
    wx = data.fetch_weather_forecast(D.strftime("%Y-%m-%d"))
    wx = wx.pivot(index="ts_utc", columns="point")
    for v in C.WEATHER_VARS:
        if "radiation" in v or v == "precipitation":
            wx[v] = wx[v].shift(-1)
    df = df.set_index("ts_utc")
    for (v, pt), col in zip(wx.columns, wx.columns):
        s = wx[col].reindex(df.index)
        m = s.notna()
        df.loc[m, f"{v}_{pt}"] = s[m]; df.loc[m, f"{v}_{pt}_d2"] = s[m]
    df = df.reset_index()
    X = build_features(df, "strict")
    X = X[X.date >= C.WEATHER_FULL_FROM]
    fc = feature_cols(X)
    train = X[X.date <= D - pd.Timedelta(days=2)]
    test = X[X.date == D].sort_values("ts_utc")
    if len(test) < 23:
        raise RuntimeError(f"target day {D.date()} has {len(test)} rows in the frame; need 23-25")
    out = {"target_date": D.strftime("%Y-%m-%d"), "issued_at_utc": issued.strftime("%Y-%m-%dT%H:%M:%SZ"),
           "origin_rule": f"features as of {C.ORIGIN_HOUR_LOCAL:02d}:00 {C.TZ} on D-1", "zone": C.ZONE, "hub": C.HUB,
           "train_rows": int(len(train)), "train_through": train.date.max().strftime("%Y-%m-%d"),
           "ts_utc": [t.strftime("%Y-%m-%dT%H:%M:%SZ") for t in test.ts_utc], "hour_local": test.hour_local.tolist(), "models": {}}
    gb = {}
    for tgt in TARGETS:
        m = GBM(fc).fit(train, train[tgt]); p = m.predict(test)
        gb[tgt] = {k: [round(float(v), 2) for v in p[k]] for k in ["yhat", "p10", "p50", "p90"]}
    out["models"]["gbm"] = gb
    if use_chronos:
        try:
            r = subprocess.run([sys.executable, "-m", "caiso_forecast.live_chronos", D.strftime("%Y-%m-%d")], capture_output=True, text=True,
                               cwd=str(C.ROOT), env={**dict(__import__("os").environ), "PYTHONPATH": "src"}, timeout=900)
            out["models"]["chronos"] = json.loads(r.stdout.strip().splitlines()[-1])
        except Exception as e:  # noqa: BLE001
            log.warning("chronos failed: %s", str(e)[:200]); out["models"]["chronos"] = {"error": str(e)[:200]}
    # naive baseline written into the record too, so the file is self-grading
    hist = df.set_index("ts_utc")
    out["models"]["naive_168"] = {tgt: {"yhat": [None if pd.isna(v) else round(float(v), 2) for v in hist[tgt].reindex(test.ts_utc - pd.Timedelta(hours=168))]} for tgt in TARGETS}
    FORECASTS.mkdir(exist_ok=True)
    path = FORECASTS / f"{D.strftime('%Y-%m-%d')}.json"
    path.write_text(json.dumps(out, indent=1))
    log.info("wrote %s (issued %s)", path.name, out["issued_at_utc"])
    return out


# ------------------------------------------------------------------ 3. grade
def grade(D: pd.Timestamp, df: pd.DataFrame) -> dict | None:
    path = FORECASTS / f"{D.strftime('%Y-%m-%d')}.json"
    if not path.exists():
        log.warning("no forecast file for %s", D.date()); return None
    f = json.loads(path.read_text())
    ts = pd.to_datetime(f["ts_utc"], utc=True)
    act = df.set_index("ts_utc").reindex(ts)
    if act.load_mw.isna().mean() > 0.2 or act.lmp_rt.isna().mean() > 0.2:
        log.warning("actuals for %s not complete yet", D.date()); return None
    rows = {"target_date": f["target_date"], "issued_at_utc": f["issued_at_utc"], "graded_at_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")}
    for tgt in TARGETS:
        y = act[tgt]
        for mname, mm in f["models"].items():
            if tgt in mm and "yhat" in mm[tgt]:
                yhat = pd.Series(mm[tgt]["yhat"], index=ts, dtype=float)
                sc = M.score(y, yhat, mape=(tgt == "load_mw"))
                rows[f"{mname}__{tgt}__MAE"] = round(sc["MAE"], 2)
                if "p10" in mm[tgt]:
                    lo, hi = pd.Series(mm[tgt]["p10"], index=ts), pd.Series(mm[tgt]["p90"], index=ts)
                    rows[f"{mname}__{tgt}__cov80"] = round(float(((y >= lo) & (y <= hi)).mean()), 3)
        if tgt == "load_mw":
            rows["caiso__load_mw__MAE"] = round(M.score(y, act.load_fc_caiso_mw)["MAE"], 2)
        if tgt == "lmp_rt":
            rows["da_lmp__lmp_rt__MAE"] = round(M.score(y, act.lmp_da)["MAE"], 2)
    rows["actual_peak_load_mw"] = round(float(y.max() if tgt == "load_mw" else act.load_mw.max()), 0)
    rows["actual_max_rt_lmp"] = round(float(act.lmp_rt.max()), 1)
    TRACK.parent.mkdir(parents=True, exist_ok=True)
    tr = pd.read_csv(TRACK) if TRACK.exists() else pd.DataFrame()
    tr = pd.concat([tr[tr.get("target_date", pd.Series(dtype=str)) != rows["target_date"]] if len(tr) else tr, pd.DataFrame([rows])], ignore_index=True)
    tr.sort_values("target_date").to_csv(TRACK, index=False)
    log.info("graded %s: gbm load MAE %s vs CAISO %s", D.date(), rows.get("gbm__load_mw__MAE"), rows.get("caiso__load_mw__MAE"))
    return rows


# ------------------------------------------------------------------ 4. site + briefing
def briefing(f: dict, df: pd.DataFrame) -> str:
    """Plain-English grid briefing generated ONLY from the forecast file's numbers (no LLM, no outside facts)."""
    g = f["models"]["gbm"]; hl = f["hour_local"]
    # narrative uses the quantile models (P50/P10/P90): the L2 mean is pulled above P90 on skewed price days
    load, p10, p90 = np.array(g["load_mw"]["p50"]), np.array(g["load_mw"]["p10"]), np.array(g["load_mw"]["p90"])
    rt, rt90, rt_mean = np.array(g["lmp_rt"]["p50"]), np.array(g["lmp_rt"]["p90"]), np.array(g["lmp_rt"]["yhat"])
    pk = int(np.argmax(load)); pr = int(np.argmax(rt))
    ramp = load[np.isin(hl, [17, 18, 19, 20])].max() - load[np.isin(hl, [13, 14, 15])].min()
    width_ev = (p90 - p10)[np.isin(hl, [17, 18, 19, 20, 21])].mean(); width_mid = (p90 - p10)[np.isin(hl, [10, 11, 12, 13, 14, 15])].mean()
    L = [f"**Grid briefing for {f['target_date']}** (issued {f['issued_at_utc']} UTC, model trained through {f['train_through']}).",
         f"Forecast peak load {load[pk]:,.0f} MW at {hl[pk]:02d}:00 local (P10–P90 {p10[pk]:,.0f}–{p90[pk]:,.0f}); "
         f"overnight minimum {load.min():,.0f} MW. Afternoon-to-evening rise about {ramp:,.0f} MW.",
         f"Real-time SP15 price: median peak ${rt[pr]:.0f}/MWh at {hl[pr]:02d}:00, P90 ${rt90[pr]:.0f} (mean-model peak ${rt_mean.max():.0f}, which sits above P90 when the day is skewed); daily median ${np.median(rt):.0f}.",
         f"Uncertainty band is {'wider' if width_ev > width_mid else 'narrower'} on the evening ramp ({width_ev:,.0f} MW) than at midday ({width_mid:,.0f} MW)."]
    if "chronos" in f["models"] and "load_mw" in f["models"]["chronos"]:
        c = np.array(f["models"]["chronos"]["load_mw"]["yhat"]); L.append(f"Chronos zero-shot peak {c.max():,.0f} MW ({'above' if c.max() > load[pk] else 'below'} ours by {abs(c.max()-load[pk]):,.0f} MW).")
    return "\n".join(L)


def render_site(df: pd.DataFrame) -> None:
    SITE.mkdir(exist_ok=True)
    tr = pd.read_csv(TRACK) if TRACK.exists() else pd.DataFrame()
    files = sorted(FORECASTS.glob("*.json"))
    latest = json.loads(files[-1].read_text()) if files else None
    brief = briefing(latest, df) if latest else "No forecast issued yet."
    (C.ROOT / "briefings" / f"{latest['target_date']}.md").write_text(brief) if latest else None
    def tbl(d: pd.DataFrame) -> str:
        return d.to_html(index=False, border=0, classes="t", float_format=lambda x: f"{x:,.1f}") if len(d) else "<p>Nothing graded yet.</p>"
    summ = ""
    if len(tr):
        cols = [c for c in tr.columns if c.endswith("__MAE")]
        agg = tr[cols].mean().rename("mean MAE").to_frame(); agg["days"] = len(tr)
        agg.index = [c.replace("__", " ").replace("_MAE", "") for c in agg.index]
        wins = (tr["gbm__load_mw__MAE"] < tr["caiso__load_mw__MAE"]).mean() if "caiso__load_mw__MAE" in tr else float("nan")
        summ = f"<p><b>{len(tr)} days graded.</b> LightGBM beat CAISO's official load forecast on <b>{100*wins:.0f}%</b> of days. " \
               f"Mean load MAE: ours {tr['gbm__load_mw__MAE'].mean():,.0f} MW vs CAISO {tr['caiso__load_mw__MAE'].mean():,.0f} MW; " \
               f"RT price MAE: ours ${tr['gbm__lmp_rt__MAE'].mean():.1f} vs DA LMP ${tr['da_lmp__lmp_rt__MAE'].mean():.1f}.</p>" + agg.reset_index().rename(columns={"index": "entrant / target"}).to_html(index=False, border=0, classes="t", float_format=lambda x: f"{x:,.1f}")
    sb = (C.ROOT / "docs" / "scoreboard.md").read_text() if (C.ROOT / "docs" / "scoreboard.md").exists() else ""
    import html as _h
    recent = tbl(tr.tail(30).iloc[::-1]) if len(tr) else ""
    page = f"""<!doctype html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>CAISO day-ahead forecaster — live track record</title>
<style>body{{font:15px/1.5 system-ui,sans-serif;max-width:1100px;margin:2rem auto;padding:0 1rem;color:#0b0b0b;background:#fcfcfb}}
.t{{border-collapse:collapse;font-size:13px;margin:.5rem 0 1.5rem}} .t td,.t th{{padding:4px 8px;border-bottom:1px solid #e6e5e1;text-align:right}} .t th{{text-align:left;background:#f3f2ee}}
pre{{white-space:pre-wrap;background:#f3f2ee;padding:1rem;border-radius:6px;font-size:13px}} img{{max-width:100%}} h2{{margin-top:2rem}} .muted{{color:#52514e}}</style></head><body>
<h1>CAISO day-ahead forecaster — live, graded record</h1>
<p class="muted">Every afternoon a job commits tomorrow's 24-hour SP15 load & real-time price forecast to the repo <i>before</i> the day-ahead market clears, then grades it against actuals the next day. Baseline that counts: CAISO's own published day-ahead load forecast; for price, the day-ahead LMP.</p>
<h2>Running record</h2>{summ}
<h2>Latest briefing</h2><pre>{_h.escape(brief)}</pre>
<h2>Last 30 graded days (MAE: MW for load, $/MWh for price)</h2>{recent}
<h2>Walk-forward tournament ({C.BACKTEST_FIRST_TARGET} → {C.BACKTEST_LAST_TARGET})</h2><pre>{_h.escape(sb)}</pre>
<h2>Figures</h2><img src="fig1_duck_by_year.png"><img src="fig5_intervals.png"><img src="fig7_battery_frontier.png">
<p class="muted">Source: <a href="https://github.com/anjalimitt2k/anjaliprojects">github.com/anjalimitt2k/anjaliprojects</a>. Rendered {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M')} UTC.</p>
</body></html>"""
    (SITE / "index.html").write_text(page)
    import shutil
    for fig in ["fig1_duck_by_year.png", "fig5_intervals.png", "fig7_battery_frontier.png"]:
        src = C.ROOT / "docs" / "eda" / fig
        if src.exists():
            shutil.copy(src, SITE / fig)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--target"); ap.add_argument("--skip-update", action="store_true"); ap.add_argument("--no-chronos", action="store_true")
    a = ap.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    for noisy in ["gridstatus", "urllib3", "requests", "httpx"]:
        logging.getLogger(noisy).setLevel(logging.ERROR)
    D = pd.Timestamp(a.target) if a.target else today_local() + pd.Timedelta(days=1)
    D = D.tz_localize(None).normalize()
    yesterday = D - pd.Timedelta(days=1)
    df = rebuild_hourly(D) if a.skip_update else update_data(yesterday)
    df.to_parquet(C.PROCESSED / "hourly_live.parquet", index=False)
    f = forecast(D, df, use_chronos=not a.no_chronos)
    grade(yesterday, df)
    render_site(df)
    print(briefing(f, df))


if __name__ == "__main__":
    main()
