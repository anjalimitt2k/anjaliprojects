"""Phase 7: are the P10–P90 bands honest? Coverage overall and by regime, a 4-bin PIT, pinball loss, and the
'intervals must widen on the evening ramp' figure. Writes docs/calibration.md + docs/eda/fig5_*.png."""
from __future__ import annotations

import numpy as np
import pandas as pd
import matplotlib; matplotlib.use("Agg")
import matplotlib.pyplot as plt
from . import config as C
from .tournament import wide, LABELS
from .eda import PAL, INK2

OUT = C.ROOT / "docs" / "eda"


def pinball(y, q, a):
    d = y - q
    return float(np.mean(np.maximum(a * d, (a - 1) * d)))


def conformalize(df: pd.DataFrame, m: str, tgt: str, window_days: int = 60) -> pd.DataFrame:
    """Split-conformal bands, per hour of day: for each day, take the empirical 10th/90th percentiles of (actual − p50)
    at each hour over the previous `window_days` graded days (strictly before the origin) and add them to p50. Leak-free: uses only
    forecasts already issued and actuals already observed by the origin."""
    d = df[["ts_utc", "date_local", "hour_local", tgt, f"{m}__{tgt}__p50" if f"{m}__{tgt}__p50" in df else f"{m}__{tgt}"]].copy()
    d.columns = ["ts_utc", "date", "hour", "y", "p50"]
    d["res"] = d.y - d.p50
    days = sorted(d.date.unique()); lo = pd.Series(np.nan, index=d.index); hi = pd.Series(np.nan, index=d.index)
    by_day = {k: g for k, g in d.groupby("date")}
    for i, day in enumerate(days):
        past = days[max(0, i - window_days - 1):i - 1]            # ends at D-2 (complete at the origin)
        if len(past) < 20:
            continue
        r = pd.concat([by_day[k][["hour", "res"]] for k in past])
        qh = r.groupby("hour").res.quantile([0.1, 0.9]).unstack()     # per-hour-of-day residual quantiles
        cur = by_day[day]
        lo[cur.index] = cur.p50 + cur.hour.map(qh[0.1]).values; hi[cur.index] = cur.p50 + cur.hour.map(qh[0.9]).values
    out = df.copy(); out[f"{m}_conf__{tgt}__p10"] = lo; out[f"{m}_conf__{tgt}__p90"] = hi; out[f"{m}_conf__{tgt}"] = d.p50
    return out


def main():
    df = wide("strict")
    for tgt in ["load_mw", "lmp_rt"]:
        if "gbm__load_mw" in df:
            df = conformalize(df, "gbm", tgt)
    LABELS["gbm_conf"] = "LightGBM + 60-day conformal bands"
    models = sorted({c.split("__")[0] for c in df.columns if c.endswith("__p10")})
    L = ["# Phase 7 — intervals & calibration (P10–P90, walk-forward)\n", "Target coverage is 80 %. PIT bins expected 10 / 40 / 40 / 10 %.\n"]
    for tgt in ["load_mw", "lmp_rt"]:
        rows = []
        for m in models:
            lo, hi, md = df.get(f"{m}__{tgt}__p10"), df.get(f"{m}__{tgt}__p90"), df.get(f"{m}__{tgt}")
            if lo is None:
                continue
            ok = lo.notna() & hi.notna() & df[tgt].notna()
            y = df[tgt][ok]; lo, hi, md = lo[ok], hi[ok], md[ok]
            inside = (y >= lo) & (y <= hi)
            splits = {"all": pd.Series(True, index=y.index), "normal": df.regime[ok] == "normal", "spike+severe": df.regime[ok] != "normal",
                      "ramp 17-21": df.ramp[ok], "midday 10-15": df.hour_local[ok].between(10, 15)}
            r = {"model": LABELS[m], "n": int(ok.sum())}
            for k, s in splits.items():
                r[f"cov {k}"] = round(100 * inside[s].mean(), 1)
            r["mean width"] = round(float((hi - lo).mean()), 1)
            pit = [float((y < lo).mean()), float(((y >= lo) & (y < md)).mean()), float(((y >= md) & (y <= hi)).mean()), float((y > hi).mean())]
            r["PIT <p10 / p10-p50 / p50-p90 / >p90 (%)"] = " / ".join(f"{100*p:.0f}" for p in pit)
            r["pinball p10/p50/p90"] = " / ".join(f"{pinball(y, q, a):.1f}" for q, a in [(lo, .1), (md, .5), (hi, .9)])
            rows.append(r)
        L.append(f"\n## target `{tgt}`\n"); L.append(pd.DataFrame(rows).set_index("model").to_markdown())
    # figure: mean width by hour (load, RT price), both models; plus one sample summer week with the band
    fig, axes = plt.subplots(1, 3, figsize=(14, 4))
    for ax, tgt, unit in [(axes[0], "load_mw", "MW"), (axes[1], "lmp_rt", "$/MWh")]:
        for m, c in zip(models, PAL):
            if f"{m}__{tgt}__p10" not in df:
                continue
            w = (df[f"{m}__{tgt}__p90"] - df[f"{m}__{tgt}__p10"]).groupby(df.hour_local).mean()
            ax.plot(w.index, w.values, color=c, lw=2, label=LABELS[m])
        ax.set_title(f"P10–P90 width by hour, {tgt}"); ax.set_xlabel("hour of day (local)"); ax.set_ylabel(unit); ax.set_xticks(range(0, 24, 3)); ax.legend(fontsize=8)
        ax.axvspan(17, 21, color=INK2, alpha=0.06, lw=0)
    ax = axes[2]
    wk = df[(df.date_local >= "2024-09-03") & (df.date_local <= "2024-09-09")]
    if "gbm__load_mw__p10" in df and len(wk):
        ax.fill_between(wk.ts_local, wk["gbm__load_mw__p10"], wk["gbm__load_mw__p90"], color=PAL[0], alpha=0.2, lw=0, label="LightGBM P10–P90")
        ax.plot(wk.ts_local, wk["gbm__load_mw"], color=PAL[0], lw=1.5, label="LightGBM P50")
        ax.plot(wk.ts_local, wk.load_mw, color="#0b0b0b", lw=1.2, label="actual")
        ax.plot(wk.ts_local, wk.load_fc_caiso_mw, color=PAL[3], lw=1.2, ls="--", label="CAISO DA")
        ax.set_title("Sep 2024 heat wave: band vs actual"); ax.set_ylabel("MW"); ax.legend(fontsize=8); ax.tick_params(axis="x", labelrotation=30, labelsize=8)
    fig.suptitle("Intervals widen where the uncertainty is: the evening ramp (shaded)", x=0.01, ha="left", fontsize=13, fontweight="semibold")
    fig.tight_layout(rect=(0, 0, 1, 0.93)); fig.savefig(OUT / "fig5_intervals.png", dpi=150); plt.close(fig)
    (C.ROOT / "docs" / "calibration.md").write_text("\n".join(L)); print("\n".join(L))


if __name__ == "__main__":
    main()
