"""Phase 2: EDA. Four figures, the spike table, the post-mortem shortlist. Writes docs/eda/*.png + docs/eda/tables.md.

Run: PYTHONPATH=src .venv/bin/python -m caiso_forecast.eda
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from . import config as C

OUT = C.ROOT / "docs" / "eda"
# reference categorical palette, fixed slot order (blue, orange, aqua, yellow); text in ink tokens
PAL = ["#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#e87ba4", "#008300"]
INK, INK2, GRID, SURF = "#0b0b0b", "#52514e", "#e6e5e1", "#fcfcfb"
plt.rcParams.update({"figure.facecolor": SURF, "axes.facecolor": SURF, "axes.edgecolor": GRID, "axes.labelcolor": INK2,
                     "xtick.color": INK2, "ytick.color": INK2, "text.color": INK, "axes.grid": True, "grid.color": GRID,
                     "grid.linewidth": 0.8, "axes.axisbelow": True, "axes.spines.top": False, "axes.spines.right": False, "font.size": 10,
                     "axes.titleweight": "semibold", "axes.titlesize": 11, "legend.frameon": False})


def load() -> pd.DataFrame:
    df = pd.read_parquet(C.PROCESSED / "hourly.parquet")
    df["year"] = df.ts_local.dt.year
    df["is_weekend"] = df.dow_local >= 5
    # 3-hour net-load ramp ending at this hour (actuals; EDA only)
    df["net_load_ramp3"] = df.net_load_mw - df.net_load_mw.shift(3)
    return df


def _label_lines(ax, x_last, series: dict[str, float], fmt="{}"):
    for (name, y), col in zip(series.items(), PAL):
        ax.annotate(fmt.format(name), (x_last, y), xytext=(4, 0), textcoords="offset points", va="center", color=col, fontsize=9)


# ---------------------------------------------------------------- Fig 1: duck curve by year
def fig_duck(df):
    fig, axes = plt.subplots(2, 2, figsize=(11, 7.2), sharex=True)
    seasons = {"Spring (Mar–May)": [3, 4, 5], "Summer (Jul–Sep)": [7, 8, 9]}
    for col, (sname, months) in enumerate(seasons.items()):
        sub = df[df.month_local.isin(months)]
        for row, (var, ylabel, title) in enumerate([("net_load_mw", "MW", f"{sname}: mean net load by hour"),
                                                     ("lmp_da", "$/MWh", f"{sname}: mean day-ahead LMP (SP15) by hour")]):
            ax = axes[row, col]
            prof = sub.groupby(["year", "hour_local"])[var].mean().unstack(0)
            prof = prof[[y for y in prof.columns if sub[sub.year == y].date_local.nunique() >= 60]]  # drop partial seasons
            years = sorted(set(df.year))
            for y in prof.columns:
                ax.plot(prof.index, prof[y], color=PAL[years.index(y)], lw=2, label=str(y))
            ax.set_title(title); ax.set_ylabel(ylabel); ax.set_xlim(0, 23); ax.set_xticks(range(0, 24, 3))
            if var == "net_load_mw":
                ax.axhline(0, color=INK2, lw=0.8, ls=":")
    for ax in axes[1]:
        ax.set_xlabel("hour of day (local)")
    handles = [plt.Line2D([], [], color=PAL[i], lw=2, label=str(y)) for i, y in enumerate(sorted(set(df.year)))]
    fig.legend(handles=handles, loc="upper right", ncol=4, bbox_to_anchor=(0.99, 0.985), fontsize=9, title="year", title_fontsize=9)
    fig.suptitle("The duck deepens: net load and day-ahead price by hour, by year", x=0.01, y=0.985, ha="left", fontsize=13, fontweight="semibold")
    fig.text(0.01, 0.935, "Net load = Outlook demand − fleet solar − wind. Seasons with < 60 days omitted.", color=INK2, fontsize=9)
    fig.tight_layout(rect=(0, 0, 1, 0.92)); fig.savefig(OUT / "fig1_duck_by_year.png", dpi=150); plt.close(fig)
    belly = df[df.month_local.isin([3, 4, 5])].groupby("year").net_load_mw.apply(lambda s: s.groupby(df.loc[s.index, "hour_local"]).mean().min())
    return belly


# ---------------------------------------------------------------- Fig 2: temperature vs load
def fig_temp(df):
    fig, axes = plt.subplots(1, 2, figsize=(11, 4.4), sharey=True)
    for ax, (pt, name) in zip(axes, [("la", "Los Angeles"), ("fres", "Fresno")]):
        t = df[f"temperature_2m_{pt}"]
        bins = np.arange(np.floor(t.min()), np.ceil(t.max()) + 1, 1.0)
        for wk, lab, c in [(False, "weekday", PAL[0]), (True, "weekend", PAL[1])]:
            s = df[(df.is_weekend == wk) & t.notna() & df.hour_local.between(14, 19)]
            g = s.groupby(pd.cut(t[s.index], bins, labels=bins[:-1] + 0.5), observed=True).load_mw
            m, lo, hi, n = g.median(), g.quantile(0.25), g.quantile(0.75), g.size()
            keep = n >= 20
            ax.fill_between(m.index[keep].astype(float), lo[keep], hi[keep], color=c, alpha=0.15, lw=0)
            ax.plot(m.index[keep].astype(float), m[keep], color=c, lw=2, label=lab)
        ax.set_title(name)
        ax.set_xlabel("forecast 2 m temperature (°C), hours 14–19"); ax.legend(loc="upper left")
    axes[0].set_ylabel("CAISO load (MW), median with IQR band")
    fig.suptitle("Afternoon load vs day-before forecast temperature: heat drives load, cold barely does", x=0.01, ha="left", fontsize=13, fontweight="semibold")
    fig.text(0.01, 0.9, "Hours 14–19. Forecast temperature (Open-Meteo previous-day run), because that is what the model will see. Bins with < 20 hours dropped.", color=INK2, fontsize=9)
    fig.tight_layout(rect=(0, 0, 1, 0.88)); fig.savefig(OUT / "fig2_temp_vs_load.png", dpi=150); plt.close(fig)


# ---------------------------------------------------------------- Fig 3 + table: spike hours
def fig_spikes(df):
    q = df.lmp_da.quantile([C.SPIKE_Q["spike"], C.SPIKE_Q["severe"]])
    thr_spike, thr_severe = float(q.iloc[0]), float(q.iloc[1])
    df["is_spike"] = df.lmp_da >= thr_spike
    df["is_severe"] = df.lmp_da >= thr_severe
    sev = df[df.is_severe]
    fig, axes = plt.subplots(1, 3, figsize=(12, 3.8))
    for ax, key, title in [(axes[0], "hour_local", "by hour of day"), (axes[1], "month_local", "by month"), (axes[2], "year", "by year")]:
        cnt = sev.groupby(key).size().reindex(sorted(df[key].unique()), fill_value=0)
        ax.bar(cnt.index.astype(str), cnt.values, color=PAL[0], width=0.72)
        ax.set_title(f"Top-1% DA price hours {title}"); ax.set_ylabel("hours" if ax is axes[0] else "")
        if key == "hour_local":
            ax.set_xticks(range(0, 24, 3)); ax.set_xticklabels([str(h) for h in range(0, 24, 3)])
    fig.suptitle(f"Where the severe hours live (DA LMP ≥ ${thr_severe:.0f}/MWh, n={len(sev)})", x=0.01, ha="left", fontsize=13, fontweight="semibold")
    fig.tight_layout(rect=(0, 0, 1, 0.92)); fig.savefig(OUT / "fig3_spike_hours.png", dpi=150); plt.close(fig)

    feats = {"lmp_da": "DA LMP $/MWh", "lmp_rt": "RT LMP $/MWh", "load_mw": "load MW", "net_load_mw": "net load MW",
             "net_load_ramp3": "3h net-load ramp MW", "solar_outlook_mw": "solar MW", "wind_outlook_mw": "wind MW",
             "temperature_2m_la": "fc temp LA °C", "temperature_2m_fres": "fc temp Fresno °C", "wind_speed_10m_fres": "fc wind Fresno m/s"}
    rows = []
    for name, mask in [("normal (<p95)", ~df.is_spike), ("spike (≥p95)", df.is_spike & ~df.is_severe), ("severe (≥p99)", df.is_severe)]:
        r = df[mask][list(feats)].median().rename(name); r["hours"] = int(mask.sum()); rows.append(r)
    tab = pd.DataFrame(rows).rename(columns=feats)
    cols = ["hours"] + list(feats.values())
    return thr_spike, thr_severe, tab[cols]


# ---------------------------------------------------------------- Fig 4: post-mortem candidates
def pick_candidates(df):
    df = df[df.date_local >= C.BACKTEST_FIRST_TARGET]  # a post-mortem needs a model forecast to exist
    # (1) heat-wave peak: day of max load. (2) negative-net-load weekend: day of min net load.
    # (3) low-wind evening-ramp spike: evening hours 17-21 with the biggest DA->RT price miss among
    #     days whose evening wind is in the bottom quartile (the history-based miss we expect to study).
    d_heat = df.loc[df.load_mw.idxmax(), "date_local"]
    d_neg = df.loc[df.net_load_mw.idxmin(), "date_local"]
    ev = df[df.hour_local.between(17, 21)].copy()
    wq = ev.groupby("date_local").wind_outlook_mw.mean()
    low_wind = wq[wq <= wq.quantile(0.25)].index
    miss = ev[ev.date_local.isin(low_wind)].groupby("date_local").apply(lambda g: (g.lmp_rt - g.lmp_da).max())
    miss = miss.drop([d_heat, d_neg], errors="ignore")
    d_ramp = miss.idxmax()
    return {"heat-wave peak": d_heat, "negative net-load weekend": d_neg, "low-wind evening ramp": d_ramp}


def fig_candidates(df, cands):
    fig, axes = plt.subplots(2, 3, figsize=(13, 6.5), sharex=True)
    for col, (label, d) in enumerate(cands.items()):
        day = df[df.date_local == d].set_index("hour_local")
        ax = axes[0, col]
        ax.plot(day.index, day.lmp_da, color=PAL[0], lw=2, label="day-ahead LMP")
        ax.plot(day.index, day.lmp_rt, color=PAL[1], lw=2, label="real-time LMP (hourly mean)")
        ax.set_title(f"{label}\n{d} ({pd.Timestamp(d).day_name()})"); ax.set_ylabel("$/MWh" if col == 0 else ""); ax.legend(loc="best", fontsize=8)
        ax = axes[1, col]
        ax.plot(day.index, day.load_mw, color=PAL[0], lw=2, label="load")
        ax.plot(day.index, day.net_load_mw, color=PAL[2], lw=2, label="net load")
        ax.plot(day.index, day.load_fc_caiso_mw, color=PAL[3], lw=1.5, ls="--", label="CAISO DA load forecast")
        ax.axhline(0, color=INK2, lw=0.8, ls=":"); ax.set_ylabel("MW" if col == 0 else ""); ax.set_xlabel("hour of day (local)")
        ax.legend(loc="best", fontsize=8); ax.set_xticks(range(0, 24, 3))
    fig.suptitle("Post-mortem candidates: what the market priced the day before vs what happened", x=0.01, ha="left", fontsize=13, fontweight="semibold")
    fig.tight_layout(rect=(0, 0, 1, 0.94)); fig.savefig(OUT / "fig4_postmortem_candidates.png", dpi=150); plt.close(fig)


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    df = load()
    belly = fig_duck(df)
    fig_temp(df)
    thr_spike, thr_severe, tab = fig_spikes(df)
    cands = pick_candidates(df)
    fig_candidates(df, cands)

    lines = ["# Phase 2 tables (generated by caiso_forecast.eda)\n"]
    lines.append("## Spring duck belly (mean net load at the minimum hour, Mar–May)\n")
    lines.append(belly.round(0).rename("MW").to_frame().to_markdown())
    lines.append(f"\n## Spike thresholds (full window, DA LMP SP15)\n\n- p95 = ${thr_spike:.1f}/MWh  - p99 = ${thr_severe:.1f}/MWh\n")
    lines.append("## Medians by regime\n"); lines.append(tab.round(1).to_markdown())
    # cost of the wrong basis
    if "load_sld_actual_mw" in df:
        ape_ok = ((df.load_mw - df.load_fc_caiso_mw).abs() / df.load_mw * 100).mean()
        ape_bad = ((df.load_sld_actual_mw - df.load_fc_caiso_mw).abs() / df.load_sld_actual_mw * 100).mean()
        lines.append(f"\n## Cost of the wrong basis\n\nCAISO DA forecast MAPE vs Outlook demand: **{ape_ok:.2f}%**; vs OASIS SLD_FCST 'ACTUAL': **{ape_bad:.2f}%**. Same forecast, different actual.\n")
    lines.append("\n## Post-mortem shortlist\n")
    for k, d in cands.items():
        day = df[df.date_local == d]
        lines.append(f"- **{k}** — {d} ({pd.Timestamp(d).day_name()}): load {day.load_mw.min():.0f}–{day.load_mw.max():.0f} MW, net load min {day.net_load_mw.min():.0f} MW, "
                     f"DA LMP max ${day.lmp_da.max():.0f}, RT LMP max ${day.lmp_rt.max():.0f} (15-min max ${day.lmp_rt_max15.max():.0f}), "
                     f"CAISO load MAPE that day {((day.load_mw-day.load_fc_caiso_mw).abs()/day.load_mw*100).mean():.1f}%")
    (OUT / "tables.md").write_text("\n".join(lines))
    print("\n".join(lines))


if __name__ == "__main__":
    main()
