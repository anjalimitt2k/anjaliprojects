"""Phase 1 gate: the hourly frame must pass these checks before any modelling starts.

Run:  .venv/bin/python -m caiso_forecast.validate   (from repo root, with src on path)
Writes data/processed/validation_report.md and exits non-zero on any FAIL.
"""
from __future__ import annotations

import sys
import pandas as pd
from . import config as C

CORE = ["load_mw", "load_fc_caiso_mw", "lmp_da", "lmp_rt", "solar_sys_mw", "wind_sys_mw",
        "solar_fc_sys_mw", "wind_fc_sys_mw", "net_load_mw", "temperature_2m_la"]


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
    for c in CORE:
        n = int(df[c].isna().sum())
        pct = 100 * n / len(df)
        lines.append(f"- {c}: {n} missing ({pct:.2f}%)")
        check(pct < 0.5, f"{c} missing < 0.5% ({pct:.2f}%)")
    imputed = df[df.load_imputed]
    lines.append(f"- load_mw imputed rows: {len(imputed)} → {sorted(imputed.date_local.unique())}")
    check(set(imputed.date_local.unique()) <= set(fall), "load imputation only on fall-back days (the Outlook feed drops that hour at source)")
    # longest run of consecutive NaNs per column
    for c in CORE:
        na = df[c].isna()
        runs = (na != na.shift()).cumsum()[na]
        longest = int(runs.value_counts().max()) if na.any() else 0
        lines.append(f"- {c}: longest NaN run {longest}h")
        check(longest <= 24, f"{c} longest NaN run <= 24h ({longest})")

    lines.append("\n## Sanity ranges")
    check(df.load_mw.between(12_000, 55_000).all(), f"load in [12, 55] GW (min {df.load_mw.min():.0f}, max {df.load_mw.max():.0f})")
    check(df.solar_sys_mw.max() > 10_000, f"system solar peaks > 10 GW (max {df.solar_sys_mw.max():.0f})")
    night = df[df.hour_local.isin([0, 1, 2, 3])]
    check(night.solar_sys_mw.abs().max() < 500, f"night solar ~0 (|max| {night.solar_sys_mw.abs().max():.0f} MW; small negatives are station load)")
    check(df.lmp_da.between(-200, 3000).all(), f"DA LMP in [-200, 3000] (min {df.lmp_da.min():.1f}, max {df.lmp_da.max():.1f})")
    check(df.lmp_rt.between(-500, 3000).all(), f"RT LMP in [-500, 3000] (min {df.lmp_rt.min():.1f}, max {df.lmp_rt.max():.1f})")
    check(df.temperature_2m_la.between(-5, 50).all(), "LA temperature in [-5, 50] C")
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
    sc = df.solar_sys_mw.corr(df.shortwave_radiation_fres)
    lines.append(f"- corr(system solar, Fresno day-before shortwave forecast) = {sc:.3f}")
    check(sc > 0.8, "solar vs forecast radiation correlation > 0.8 → weather join hour-aligned")
    solar_peak_hr = df.groupby("hour_local").solar_sys_mw.mean().idxmax()
    check(11 <= solar_peak_hr <= 14, f"mean solar peaks at local hour {solar_peak_hr} (expect 11–14)")
    load_peak_hr = df[df.month_local.isin([7, 8, 9])].groupby("hour_local").load_mw.mean().idxmax()
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
