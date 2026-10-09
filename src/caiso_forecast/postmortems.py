"""Phase 11: named-event post-mortems. One page each: what the model said the day before, what happened hour by
hour, where the P10–P90 band broke, what forward-looking signal would have caught it. Generated from the
walk-forward forecasts (so 'what the model said' is exactly what it would have issued that afternoon)."""
from __future__ import annotations

import numpy as np
import pandas as pd
import matplotlib; matplotlib.use("Agg")
import matplotlib.pyplot as plt
from . import config as C
from .tournament import wide
from .calibration import conformalize
from .eda import PAL, INK2

OUT = C.ROOT / "docs" / "postmortems"
EVENTS = {"2024-09-05": "Heat-wave peak (load record 47.3 GW)", "2026-06-20": "Negative net-load Saturday (−8.9 GW)", "2026-03-20": "Low-wind evening ramp (RT $1,188 15-min)"}


def page(df: pd.DataFrame, d: str, title: str) -> str:
    g = df[df.date_local == d].sort_values("ts_utc").set_index("hour_local")
    prev = df[df.date_local == (pd.Timestamp(d) - pd.Timedelta(days=1)).strftime("%Y-%m-%d")]
    lo, hi = g["gbm_conf__load_mw__p10"], g["gbm_conf__load_mw__p90"]
    broke = g[(g.load_mw < lo) | (g.load_mw > hi)]
    plo, phi = g["gbm_conf__lmp_rt__p10"], g["gbm_conf__lmp_rt__p90"]
    pbroke = g[(g.lmp_rt < plo) | (g.lmp_rt > phi)]
    sp = pd.read_parquet(C.PROCESSED / "spike_probs.parquet")
    p_spike = float(sp.loc[pd.Timestamp(d), "p"]) if pd.Timestamp(d) in sp.index else float("nan")
    pk = g.load_mw.idxmax(); ppk = g.lmp_rt.idxmax()
    L = [f"# Post-mortem — {d} ({pd.Timestamp(d).day_name()}): {title}\n",
         f"![{d}]({d}.png)\n",
         "## What the desk had the day before (issued from the 09:00 D-1 origin)\n",
         f"- **Load**: our P50 peak {g['gbm__load_mw__p50'].max():,.0f} MW at {g['gbm__load_mw__p50'].idxmax():02d}:00, conformal P10–P90 at that hour "
         f"{lo[g['gbm__load_mw__p50'].idxmax()]:,.0f}–{hi[g['gbm__load_mw__p50'].idxmax()]:,.0f}. CAISO's official DA forecast peak {g.load_fc_caiso_mw.max():,.0f} MW. "
         f"Chronos peak {g['chronos__load_mw'].max():,.0f} MW. Seasonal-naive {g.load_naive_168.max():,.0f} MW.",
         f"- **Price**: our P50 RT peak ${g['gbm__lmp_rt__p50'].max():.0f} at {g['gbm__lmp_rt__p50'].idxmax():02d}:00 (P90 ${phi.max():.0f}); the DA market cleared its peak at ${g.lmp_da.max():.0f} at {g.lmp_da.idxmax():02d}:00. "
         f"Evening-spike probability from the classifier: **{p_spike:.2f}**.",
         f"- **Inputs that day**: forecast Fresno max {g.temperature_2m_fres.max():.0f} °C, LA max {g.temperature_2m_la.max():.0f} °C; CAISO DA solar forecast peak {g.solar_fc_sys_mw.max():,.0f} MW, "
         f"evening (17–21) wind forecast mean {g.loc[17:21, 'wind_fc_sys_mw'].mean():,.0f} MW; day-before actual peak load {prev.load_mw.max():,.0f} MW.",
         "\n## What happened, hour by hour\n"]
    tab = g[["load_mw", "gbm__load_mw__p50", "load_fc_caiso_mw", "net_load_mw", "lmp_da", "lmp_rt", "lmp_rt_max15", "gbm__lmp_rt__p50"]].round(0)
    tab.columns = ["load", "ours P50", "CAISO DA", "net load", "DA LMP", "RT LMP", "RT 15-min max", "ours RT P50"]
    L.append(tab.loc[[0, 3, 6, 9, 12, 14, 15, 16, 17, 18, 19, 20, 21, 23]].to_markdown())
    L.append(f"\nActual peak load {g.load_mw.max():,.0f} MW at {pk:02d}:00; net-load minimum {g.net_load_mw.min():,.0f} MW; 3-hour evening net-load ramp "
             f"{(g.net_load_mw.loc[19] - g.net_load_mw.loc[16]):,.0f} MW. RT price peak ${g.lmp_rt.max():.0f} (hourly) / ${g.lmp_rt_max15.max():.0f} (15-min) at {ppk:02d}:00.\n")
    L.append("## Where the band broke\n")
    L.append(f"- Load: actual fell outside our conformal P10–P90 in **{len(broke)} of 24 hours** (hours {list(broke.index)}), worst miss {(broke.load_mw - broke['gbm__load_mw__p50']).abs().max() if len(broke) else 0:,.0f} MW. "
             f"CAISO's error on the peak hour was {g.load_fc_caiso_mw[pk] - g.load_mw[pk]:+,.0f} MW; ours {g['gbm__load_mw__p50'][pk] - g.load_mw[pk]:+,.0f} MW.")
    L.append(f"- Price: actual RT outside our band in **{len(pbroke)} of 24 hours** (hours {list(pbroke.index)}). At the price peak the DA market said ${g.lmp_da[ppk]:.0f}, we said ${g['gbm__lmp_rt__p50'][ppk]:.0f} (P90 ${phi[ppk]:.0f}), actual ${g.lmp_rt[ppk]:.0f}.")
    L.append(f"- Day MAE: load ours {abs(g['gbm__load_mw'] - g.load_mw).mean():,.0f} MW vs CAISO {abs(g.load_fc_caiso_mw - g.load_mw).mean():,.0f} MW vs Chronos {abs(g['chronos__load_mw'] - g.load_mw).mean():,.0f} MW; "
             f"RT price ours ${abs(g['gbm__lmp_rt'] - g.lmp_rt).mean():.0f} vs DA LMP ${abs(g.lmp_da - g.lmp_rt).mean():.0f}.\n")
    return "\n".join(L), g


def figure(g: pd.DataFrame, d: str, title: str):
    fig, axes = plt.subplots(1, 2, figsize=(13, 4.4))
    ax = axes[0]
    ax.fill_between(g.index, g["gbm_conf__load_mw__p10"], g["gbm_conf__load_mw__p90"], color=PAL[0], alpha=0.18, lw=0, label="ours P10–P90 (conformal)")
    ax.plot(g.index, g["gbm__load_mw__p50"], color=PAL[0], lw=2, label="ours P50")
    ax.plot(g.index, g.load_fc_caiso_mw, color=PAL[3], lw=1.6, ls="--", label="CAISO DA forecast")
    ax.plot(g.index, g["chronos__load_mw"], color=PAL[2], lw=1.4, ls=":", label="Chronos")
    ax.plot(g.index, g.load_mw, color="#0b0b0b", lw=2, label="actual")
    ax.set_title("Load (MW)"); ax.set_xlabel("hour of day (local)"); ax.set_xticks(range(0, 24, 3)); ax.legend(fontsize=8)
    ax = axes[1]
    ax.fill_between(g.index, g["gbm_conf__lmp_rt__p10"], g["gbm_conf__lmp_rt__p90"], color=PAL[0], alpha=0.18, lw=0, label="ours P10–P90 (conformal)")
    ax.plot(g.index, g["gbm__lmp_rt__p50"], color=PAL[0], lw=2, label="ours RT P50")
    ax.plot(g.index, g.lmp_da, color=PAL[1], lw=1.6, ls="--", label="DA LMP (market)")
    ax.plot(g.index, g.lmp_rt, color="#0b0b0b", lw=2, label="actual RT (hourly)")
    ax.plot(g.index, g.lmp_rt_max15, color=INK2, lw=1, ls=":", label="actual RT 15-min max")
    ax.set_title("SP15 price ($/MWh)"); ax.set_xlabel("hour of day (local)"); ax.set_xticks(range(0, 24, 3)); ax.legend(fontsize=8)
    fig.suptitle(f"{d} — {title}: what was said the day before vs what happened", x=0.01, ha="left", fontsize=13, fontweight="semibold")
    fig.tight_layout(rect=(0, 0, 1, 0.92)); fig.savefig(OUT / f"{d}.png", dpi=150); plt.close(fig)


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    df = wide("strict")
    for tgt in ["load_mw", "lmp_rt"]:
        df = conformalize(df, "gbm", tgt)
    for d, title in EVENTS.items():
        text, g = page(df, d, title)
        figure(g, d, title)
        (OUT / f"{d}.md").write_text(text)
        print(text.split("\n## What happened")[0]); print("...\n")


if __name__ == "__main__":
    main()
