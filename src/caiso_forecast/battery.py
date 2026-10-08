"""Phase 9: the dollarized decision layer. A 1 MW / 4 MWh battery, 90 % round-trip, one cycle per day, scheduled
day-ahead on each model's hourly price forecast and settled at actual real-time prices, blind through the backtest.
Perfect foresight = the same optimiser on actual prices (the ceiling). Risk sweep: a trade is committed only if the
forecast spread (best-4 sell − best-4 buy) exceeds a threshold; sweeping it traces revenue vs downside.
Writes docs/battery.md + fig7."""
from __future__ import annotations

import numpy as np
import pandas as pd
from scipy.optimize import linprog
import matplotlib; matplotlib.use("Agg")
import matplotlib.pyplot as plt
from . import config as C
from .tournament import wide, LABELS
from .eda import PAL, INK2

OUT = C.ROOT / "docs" / "eda"
P_MW, E_MWH, ETA = 1.0, 4.0, 0.90  # power, energy, round-trip efficiency


def schedule(prices: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """LP: maximise sum(p*(dis - ch)) s.t. SoC in [0,E], |ch|,|dis| <= P, total charge <= E (one cycle), SoC(end)=0."""
    n = len(prices)
    c = np.concatenate([prices, -prices * np.sqrt(ETA)])            # minimise -(revenue); ch costs p, dis earns p*sqrt(eta)
    # SoC_t = sqrt(eta)*cumsum(ch) - cumsum(dis)/... keep it simple: SoC = cumsum(ch*sqrt(eta) - dis/sqrt(eta))
    L = np.tril(np.ones((n, n)))
    A_soc = np.hstack([L * np.sqrt(ETA), -L / np.sqrt(ETA)])
    A_ub = np.vstack([A_soc, -A_soc, np.concatenate([np.ones(n), np.zeros(n)])[None, :]])
    b_ub = np.concatenate([np.full(n, E_MWH), np.zeros(n), [E_MWH]])
    A_eq = A_soc[-1:]; b_eq = [0.0]
    res = linprog(c, A_ub=A_ub, b_ub=b_ub, A_eq=A_eq, b_eq=b_eq, bounds=[(0, P_MW)] * (2 * n), method="highs")
    x = res.x if res.success else np.zeros(2 * n)
    return x[:n], x[n:]


def settle(ch, dis, actual):
    return float(np.sum(actual * (dis * np.sqrt(ETA) - ch)))


def main():
    W = wide("strict")
    entrants = {"perfect foresight": "lmp_rt", "DA LMP (market)": "lmp_rt_da", "seasonal-naive RT (D-7)": "lmp_rt_naive_168"}
    for m in ["gbm", "chronos"]:
        if f"{m}__lmp_rt" in W:
            entrants[LABELS[m]] = f"{m}__lmp_rt"
    days = []
    for d, g in W.groupby("date_local"):
        if len(g) < 23 or g.lmp_rt.isna().any() or any(g[c].isna().any() for c in entrants.values()):
            continue
        row = {"date": d}
        for name, col in entrants.items():
            ch, dis = schedule(g[col].values)
            row[name] = settle(ch, dis, g.lmp_rt.values)
            if name != "perfect foresight":
                fc = np.sort(g[col].values); row[f"{name}__spread"] = fc[-4:].mean() - fc[:4].mean()
        days.append(row)
    R = pd.DataFrame(days).set_index("date")
    R.to_parquet(C.PROCESSED / "battery_daily.parquet")
    perf = R["perfect foresight"].sum()
    L = [f"# Phase 9 — battery replay ({P_MW:.0f} MW / {E_MWH:.0f} MWh, {ETA:.0%} round-trip, 1 cycle/day), {R.index.min()} → {R.index.max()}, {len(R)} days\n",
         "Schedule optimised on each entrant's day-ahead price forecast; settled at actual SP15 real-time hourly LMP. Perfect foresight = ceiling.\n"]
    rows = []
    for name in entrants:
        s = R[name]
        rows.append({"entrant": name, "revenue $": round(s.sum()), "$/MW-day": round(s.mean(), 1), "% of perfect foresight": round(100 * s.sum() / perf, 1),
                     "losing days": int((s < 0).sum()), "worst day $": round(s.min(), 1), "p5 day $": round(s.quantile(.05), 1)})
    L.append(pd.DataFrame(rows).set_index("entrant").to_markdown())
    # by year
    L.append("\n\nRevenue by year ($):\n")
    L.append(R[list(entrants)].groupby(pd.to_datetime(R.index).year).sum().round(0).to_markdown())
    # risk sweep: commit only when forecast spread >= tau
    sweep = []
    for name in [n for n in entrants if n != "perfect foresight"]:
        for tau in [0, 5, 10, 15, 20, 30, 40, 60]:
            on = R[f"{name}__spread"] >= tau
            s = R[name].where(on, 0.0)
            sweep.append({"entrant": name, "min spread $/MWh": tau, "days traded": int(on.sum()), "revenue $": round(s.sum()), "p5 day $": round(s.quantile(.05), 1), "std day $": round(s.std(), 1)})
    S = pd.DataFrame(sweep)
    L.append("\n\n## Risk-tolerance sweep (trade only if the forecast's best-4-minus-worst-4 spread ≥ threshold)\n")
    L.append(S.to_markdown(index=False))
    fig, ax = plt.subplots(figsize=(7.5, 4.6))
    for (name, g), c in zip(S.groupby("entrant", sort=False), PAL):
        ax.plot(g["p5 day $"], g["revenue $"], "o-", color=c, lw=2, ms=5, label=name)
        for _, r in g.iloc[[0, -1]].iterrows():
            ax.annotate(f"τ={r['min spread $/MWh']:.0f}", (r["p5 day $"], r["revenue $"]), xytext=(4, 4), textcoords="offset points", fontsize=7, color=INK2)
    ax.axhline(perf, color=INK2, lw=1, ls=":"); ax.annotate("perfect foresight", (ax.get_xlim()[0], perf), xytext=(4, 4), textcoords="offset points", fontsize=8, color=INK2)
    ax.set_xlabel("downside: 5th-percentile daily revenue ($, higher = safer)"); ax.set_ylabel("total revenue over backtest ($)")
    ax.set_title("Revenue / risk frontier by forecast source", loc="left", fontweight="semibold"); ax.legend(fontsize=8)
    fig.tight_layout(); fig.savefig(OUT / "fig7_battery_frontier.png", dpi=150); plt.close(fig)
    (C.ROOT / "docs" / "battery.md").write_text("\n".join(L)); print("\n".join(L))


if __name__ == "__main__":
    main()
