"""Phase 3: baselines first. Every later claim is relative to these.

Load target  : `load_mw`.  Incumbent = CAISO's own DA forecast. Naive = same hour 7 days earlier.
Price target : `lmp_rt`.   Incumbent = the DA LMP itself (the market's forecast of real time). Naive = RT same hour D-7.
Both naives are computable at the 09:00 D-1 origin (D-7 and D-2 are complete by then; D-1 is not).
"""
from __future__ import annotations

import pandas as pd
from . import config as C, metrics as M


def build(df: pd.DataFrame) -> pd.DataFrame:
    df = df.set_index("ts_utc").sort_index()
    out = pd.DataFrame(index=df.index)
    out["load_naive_168"] = df.load_mw.shift(168)
    out["load_naive_48"] = df.load_mw.shift(48)
    out["load_caiso"] = df.load_fc_caiso_mw
    out["lmp_rt_naive_168"] = df.lmp_rt.shift(168)
    out["lmp_rt_da"] = df.lmp_da
    out["lmp_da_naive_168"] = df.lmp_da.shift(168)
    out["lmp_da_naive_48"] = df.lmp_da.shift(48)
    return out.reset_index()


def main():
    df = pd.read_parquet(C.PROCESSED / "hourly.parquet")
    thr = M.spike_thresholds(df)
    base = build(df)
    full = df.merge(base, on="ts_utc")
    full = M.add_regimes(full, thr)
    bt = full[(full.date_local >= C.BACKTEST_FIRST_TARGET) & (full.date_local <= C.BACKTEST_LAST_TARGET)]

    tabs = {
        "load_mw": M.score_table(bt, "load_mw", {"CAISO official DA forecast": "load_caiso", "seasonal-naive (D-7)": "load_naive_168", "naive (D-2)": "load_naive_48"}, mape=True),
        "lmp_rt": M.score_table(bt, "lmp_rt", {"DA LMP (market's forecast)": "lmp_rt_da", "seasonal-naive RT (D-7)": "lmp_rt_naive_168"}, mape=False),
        "lmp_da": M.score_table(bt, "lmp_da", {"seasonal-naive DA (D-7)": "lmp_da_naive_168", "naive DA (D-2)": "lmp_da_naive_48"}, mape=False),
    }
    base.to_parquet(C.PROCESSED / "forecasts_baselines.parquet", index=False)
    allm = pd.concat([t.assign(target=k) for k, t in tabs.items()])
    allm.to_csv(C.PROCESSED / "baselines_metrics.csv", index=False)

    L = [f"# Phase 3 — baselines (backtest window {C.BACKTEST_FIRST_TARGET} → {C.BACKTEST_LAST_TARGET})\n",
         f"Spike thresholds (DA LMP, full window): spike ≥ ${thr['spike']:.1f}/MWh, severe ≥ ${thr['severe']:.1f}/MWh.\n"]
    for tgt, t in tabs.items():
        L.append(f"\n## target `{tgt}`\n")
        cols = ["n", "MAE", "RMSE", "bias"] + (["MAPE"] if "MAPE" in t else [])
        piv = t[t.split.isin(["all", "regime=normal", "spike+severe", "regime=severe", "ramp hours 17-21"])].pivot(index="split", columns="model", values="MAE").round(1)
        L.append("MAE by split:\n"); L.append(piv.to_markdown())
        L.append("\n\nAll metrics, split = all:\n")
        L.append(t[t.split == "all"].set_index("model")[cols].round(2).to_markdown())
        L.append("\n\nBy season (MAE):\n")
        L.append(t[t.split.str.startswith("season")].pivot(index="split", columns="model", values="MAE").round(1).to_markdown())
    (C.ROOT / "docs" / "baselines.md").write_text("\n".join(L))
    print("\n".join(L))


if __name__ == "__main__":
    main()
