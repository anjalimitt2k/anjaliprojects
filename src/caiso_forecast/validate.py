"""Phase 1 gate: the hourly frame must pass these checks before any modelling starts.

Run:  .venv/bin/python -m caiso_forecast.validate   (from repo root, with src on path)
Writes data/processed/validation_report.md and exits non-zero on any FAIL.
"""
from __future__ import annotations

import sys
import pandas as pd
from . import config as C

WEATHER_COLS = {"temperature_2m_la", "shortwave_radiation_fres"}
CORE = ["load_mw", "load_fc_caiso_mw", "lmp_da", "lmp_rt", "solar_outlook_mw", "wind_outlook_mw",
        "solar_sys_mw", "wind_sys_mw", "solar_fc_sys_mw", "wind_fc_sys_mw", "net_load_mw",
        "temperature_2m_la", "shortwave_radiation_fres"]


def dst_days(start: str, end: str, tz: str) -> tuple[list[str], list[str]]:
    """Local dates with 23 (spring-forward) and 25 (fall-back) hours, derived from tz rules."""
    idx = pd.date_range(pd.Timestamp(start, tz=tz), pd.Timestamp(end, tz=tz) + pd.Timedelta(hours=23), freq="h")
    n = pd.Series(1, index=idx).groupby(idx.date).sum()
    return [str(d) for d in n[n == 23].index], [str(d) for d in n[n == 25].index]


def run(df: pd.DataFrame) -> tuple[list[str], list[str]]:
    lines, fails = [], []

    def check(ok: bool, msg: str):
        tag = "PASS" if ok else "FAIL"
        lines.append(f"- [{tag}] {msg}")
        if not ok:
            fails.append(msg)

    lines.append(f"# Phase 1 validation — hourly.parquet\n")
    lines.append(f"Window (local): {C.START} → {C.END}  | zone {C.ZONE}, hub {C.HUB}\n")
    lines.append("## Index integrity")
    expected = pd.date_range(pd.Timestamp(C.START, tz=C.TZ), pd.Timestamp(C.END, tz=C.TZ) + pd.Timedelta(hours=23), freq="h")
    check(len(df) == len(expected), f"row count {len(df)} == expected {len(expected)} hours")
    check(df.ts_utc.is_monotonic_increasing and df.ts_utc.is_unique, "ts_utc strictly increasing, no duplicates")
    diffs = df.ts_utc.diff().dropna().unique()
    check(len(diffs) == 1 and diffs[0] == pd.Timedelta(hours=1), f"every step is exactly 1h (unique diffs: {list(diffs)})")

    lines.append("\n## DST transition days (local clock)")
    per_day = df.groupby("date_local").size()
    spring, fall = dst_days(C.START, C.END, C.TZ)
    for d in spring:
        check(per_day.get(d) == 23, f"spring-forward {d}: {per_day.get(d)} rows (expect 23)")
    for d in fall:
        check(per_day.get(d) == 25, f"fall-back {d}: {per_day.get(d)} rows (expect 25)")
    normal = per_day.drop(spring + fall, errors="ignore")
    check((normal == 24).all(), f"all other days have 24 rows (offenders: {normal[normal != 24].to_dict()})")
    hour2_on_spring = df[df.date_local.isin(spring) & (df.hour_local == 2)]
    check(len(hour2_on_spring) == 0, "no local 02:00 rows on spring-forward days")
    hour1_on_fall = df[df.date_local.isin(fall) & (df.hour_local == 1)]
    check(len(hour1_on_fall) == 2 * len(fall), f"exactly two local 01:00 rows on each fall-back day ({len(hour1_on_fall)} found)")

    lines.append("\n## Missing hours per core column")
    wx_from = pd.Timestamp(C.WEATHER_FULL_FROM, tz=C.TZ).tz_convert("UTC")
    for c in CORE:
        sub = df[df.ts_utc >= wx_from] if c in WEATHER_COLS else df
        n = int(sub[c].isna().sum())
        pct = 100 * n / len(sub)
        scope = f" (from {C.WEATHER_FULL_FROM})" if c in WEATHER_COLS else ""
        lines.append(f"- {c}: {n} missing ({pct:.2f}%){scope}")
        check(pct < 0.5, f"{c} missing < 0.5% ({pct:.2f}%){scope}")
    pre = df[df.ts_utc < wx_from]
    if len(pre):
        lines.append(f"- pre-{C.WEATHER_FULL_FROM} rows: {len(pre)}; temperature coverage {100*pre.temperature_2m_la.notna().mean():.1f}%, "
                     f"radiation coverage {100*pre.shortwave_radiation_fres.notna().mean():.1f}% (archive limitation, documented)")
    gap_hours = df[df.load_mw.isna()]
    lines.append(f"- load_mw unfilled gap hours: {len(gap_hours)} on dates {sorted(gap_hours.date_local.unique())}")
    imputed = df[df.load_imputed]
    lines.append(f"- load_mw imputed rows: {len(imputed)} → {sorted(imputed.date_local.unique())}")
    check(set(imputed.date_local.unique()) <= set(fall), "load imputation only on fall-back days (the Outlook feed drops that hour at source)")
    check(len(imputed) == len(fall), f"exactly one imputed load hour per fall-back day ({len(imputed)} vs {len(fall)})")
    # longest run of consecutive NaNs per column
    for c in CORE:
        na = (df[df.ts_utc >= wx_from] if c in WEATHER_COLS else df)[c].isna()
        runs = (na != na.shift()).cumsum()[na]
        longest = int(runs.value_counts().max()) if na.any() else 0
        lines.append(f"- {c}: longest NaN run {longest}h")
        check(longest <= 24, f"{c} longest NaN run <= 24h ({longest})")

    lines.append("\n## Sanity ranges")
    check(df.load_mw.dropna().between(9_000, 55_000).all(), f"load in [9, 55] GW (min {df.load_mw.min():.0f}, max {df.load_mw.max():.0f}; ~11 GW spring-Sunday-midday lows are real BTM-solar records)")
    check(df.solar_outlook_mw.max() > 10_000, f"fleet solar peaks > 10 GW (max {df.solar_outlook_mw.max():.0f})")
    night = df[df.hour_local.isin([0, 1, 2, 3])]
    n_bad = int((night.solar_outlook_mw.abs() > 500).sum())
    check(n_bad <= 3, f"night solar ~0: {n_bad} hours with |solar| > 500 MW at 00-03h (|max| {night.solar_outlook_mw.abs().max():.0f}; small negatives are station load)")
    check(df.net_load_mw.dropna().min() > -12_000, f"net load above plausible floor -12 GW (min {df.net_load_mw.min():.0f} at {df.loc[df.net_load_mw.idxmin(), 'ts_local']})")
    check(df.solar_outlook_mw.dropna().max() < 26_000, f"fleet solar below 26 GW capability ceiling (max {df.solar_outlook_mw.max():.0f})")
    check(df.wind_outlook_mw.dropna().max() < 10_000, f"wind below 10 GW (max {df.wind_outlook_mw.max():.0f})")
    check(df.lmp_da.dropna().between(-200, 3000).all(), f"DA LMP in [-200, 3000] (min {df.lmp_da.min():.1f}, max {df.lmp_da.max():.1f})")
    check(df.lmp_rt.dropna().between(-500, 3000).all(), f"RT LMP in [-500, 3000] (min {df.lmp_rt.min():.1f}, max {df.lmp_rt.max():.1f})")
    check(df.temperature_2m_la.dropna().between(-5, 50).all(), f"LA temperature in [-5, 50] C (min {df.temperature_2m_la.min():.1f}, max {df.temperature_2m_la.max():.1f})")
    check((df.lmp_rt_n15.fillna(0) <= 4).all() and (df.load_n5min.fillna(0) <= 12).all(), "no over-full hours (>4 RT intervals or >12 5-min intervals)")

    lines.append("\n## Cross-source consistency (catches wrong-series / misaligned joins)")
    ape = ((df.load_mw - df.load_fc_caiso_mw).abs() / df.load_mw * 100)
    mape = ape.mean()
    lines.append(f"- CAISO official DA load forecast MAPE vs actual: {mape:.2f}%  (published ~1.5–3%; a solar-shaped 7%+ gap means the wrong actual series)")
    check(mape < 4, "CAISO DA forecast MAPE < 4%")
    by_hour = ape.groupby(df.hour_local).mean()
    lines.append(f"- worst hour-of-day APE: h{by_hour.idxmax()} = {by_hour.max():.2f}%")
    check(by_hour.max() < 6, "no hour-of-day with CAISO APE > 6% (midday bulge = BTM-solar series mismatch)")
    corr = df[["lmp_da", "lmp_rt"]].corr().iloc[0, 1]
    lines.append(f"- corr(DA LMP, RT LMP) = {corr:.3f}")
    check(corr > 0.5, "DA/RT LMP correlation > 0.5 (misaligned hours would destroy this)")
    lag = df.lmp_da.corr(df.lmp_rt.shift(1))
    check(corr > lag, f"DA/RT correlation at lag 0 ({corr:.3f}) beats lag 1 ({lag:.3f}) → hours aligned")
    sc = {k: df.solar_outlook_mw.corr(df.shortwave_radiation_fres.shift(k)) for k in (-1, 0, 1)}
    lines.append(f"- corr(fleet solar, Fresno day-before shortwave fc) at shift -1/0/+1h: {sc[-1]:.3f} / {sc[0]:.3f} / {sc[1]:.3f}")
    check(sc[0] > 0.9 and sc[0] > max(sc[-1], sc[1]), "solar vs forecast radiation peaks at lag 0 (>0.9) → weather hour-aligned after preceding-hour shift")
    oc = df.solar_outlook_mw.corr(df.solar_sys_mw)
    check(oc > 0.98, f"Outlook fleet solar vs OASIS solar actual correlation {oc:.3f} > 0.98 (same timing, different scope)")
    ratio = (df.solar_sys_mw.sum() / df.solar_outlook_mw.sum())
    lines.append(f"- OASIS solar / Outlook solar energy ratio = {ratio:.3f} (OASIS scope is narrower; document, don't 'fix')")
    if "net_demand_caiso_mw" in df:
        nc = df.net_load_mw.corr(df.net_demand_caiso_mw)
        check(nc > 0.995, f"our net load vs CAISO's published net demand: corr {nc:.4f} > 0.995 (timing identical)")
        mid = df[df.solar_outlook_mw > 5000]
        ratio = ((mid.net_demand_caiso_mw - mid.net_load_mw) / mid.solar_outlook_mw)
        lines.append(f"- CAISO net demand minus ours, as a share of solar (solar>5GW hours): median {ratio.median():.3f}, IQR {ratio.quantile(.25):.3f}-{ratio.quantile(.75):.3f}")
        check(0.03 < ratio.median() < 0.20, "CAISO subtracts ~9-12% less solar than its published Solar column (documented scope gap; stable, not a bug)")
        night = df[df.solar_outlook_mw < 200]
        nr = (night.net_demand_caiso_mw - night.net_load_mw).abs().median()
        check(nr < 300, f"at night our net load and CAISO's agree within {nr:.0f} MW (so the gap is solar-scope only)")
    solar_peak_hr = df.groupby("hour_local").solar_outlook_mw.mean().idxmax()
    check(10 <= solar_peak_hr <= 14, f"mean fleet solar peaks at local hour {solar_peak_hr} (expect 10–14; the fleet plateaus 10–14)")
    nl_min_hr = df.groupby("hour_local").net_load_mw.mean().idxmin()
    check(10 <= nl_min_hr <= 15, f"duck-curve belly: mean net load minimum at local hour {nl_min_hr} (expect 10–15)")
    summer = df[df.month_local.isin([7, 8, 9])]
    if len(summer):
        load_peak_hr = summer.groupby("hour_local").load_mw.mean().idxmax()
        check(16 <= load_peak_hr <= 20, f"summer load peaks at local hour {load_peak_hr} (expect 16–20)")
    tc = df.temperature_2m_la.groupby(df.hour_local).mean().idxmax()
    check(13 <= tc <= 17, f"LA temperature peaks at local hour {tc} (expect 13–17)")
    pub_lead = (df.ts_utc - df.load_fc_publish_utc).dt.total_seconds() / 3600
    lines.append(f"- CAISO DA forecast publish lead: min {pub_lead.min():.1f}h, median {pub_lead.median():.1f}h")
    check(pub_lead.min() >= 12, "every CAISO DA forecast was published >= 12h before the target hour (it is truly day-ahead)")

    lines.append("\n## Summary stats")
    lines.append(df[CORE].describe().T[["count", "mean", "min", "50%", "max"]].round(1).to_markdown())
    lines.append(f"\n**{len(fails)} FAIL / {sum(l.startswith('- [PASS]') for l in lines)} PASS**")
    return lines, fails


def main():
    df = pd.read_parquet(C.PROCESSED / "hourly.parquet")
    lines, fails = run(df)
    report = "\n".join(lines)
    (C.PROCESSED / "validation_report.md").write_text(report)
    print(report)
    sys.exit(1 if fails else 0)


if __name__ == "__main__":
    main()
