"""Phase 6 output: one scoreboard. Merges every forecasts_*.parquet with the baselines and scores them with
metrics.score_table on identical rows. Writes docs/scoreboard.md + data/processed/tournament_metrics.csv."""
from __future__ import annotations

import glob
import pandas as pd
from . import config as C, metrics as M

LABELS = {"gbm": "LightGBM (ours)", "chronos": "Chronos-Bolt zero-shot", "load_caiso": "CAISO official DA forecast",
          "load_naive_168": "seasonal-naive (D-7)", "lmp_rt_da": "DA LMP (market)", "lmp_rt_naive_168": "seasonal-naive RT (D-7)",
          "lmp_da_naive_168": "seasonal-naive DA (D-7)", "lmp_da_naive_48": "naive DA (D-2)"}
BASE = {"load_mw": ["load_caiso", "load_naive_168"], "lmp_rt": ["lmp_rt_da", "lmp_rt_naive_168"], "lmp_da": ["lmp_da_naive_48", "lmp_da_naive_168"]}


def load_forecasts(variant="strict") -> pd.DataFrame:
    fs = [pd.read_parquet(p) for p in glob.glob(str(C.PROCESSED / f"forecasts_{variant}_*.parquet"))]
    return pd.concat(fs, ignore_index=True) if fs else pd.DataFrame(columns=["model", "target", "ts_utc", "yhat", "p10", "p50", "p90", "variant"])


def wide(variant="strict") -> pd.DataFrame:
    """hourly frame + baselines + one column per (model,target) prediction, restricted to the backtest window."""
    df = pd.read_parquet(C.PROCESSED / "hourly.parquet")
    base = pd.read_parquet(C.PROCESSED / "forecasts_baselines.parquet")
    df = df.merge(base, on="ts_utc")
    f = load_forecasts(variant)
    for (m, t), g in f.groupby(["model", "target"]):
        df = df.merge(g[["ts_utc", "yhat", "p10", "p50", "p90"]].rename(columns={"yhat": f"{m}__{t}", "p10": f"{m}__{t}__p10", "p50": f"{m}__{t}__p50", "p90": f"{m}__{t}__p90"}), on="ts_utc", how="left")
    df = M.add_regimes(df, M.spike_thresholds(df))
    return df[(df.date_local >= C.BACKTEST_FIRST_TARGET) & (df.date_local <= C.BACKTEST_LAST_TARGET)].reset_index(drop=True)


def main():
    df = wide("strict")
    models_here = sorted({c.split("__")[0] for c in df.columns if "__" in c and not c.endswith(("p10", "p50", "p90"))})
    allm, L = [], [f"# Tournament scoreboard — walk-forward {C.BACKTEST_FIRST_TARGET} → {C.BACKTEST_LAST_TARGET}\n",
                   "Identical rows, identical splits for every entrant. Spike/severe = hours whose actual DA LMP ≥ p95 / p99 of the full window. "
                   "Weather features: strict variant (no run newer than the 09:00 D-1 origin).\n"]
    for tgt in ["load_mw", "lmp_rt", "lmp_da"]:
        cols = {LABELS[m]: f"{m}__{tgt}" for m in models_here if f"{m}__{tgt}" in df}
        cols.update({LABELS[b]: b for b in BASE[tgt]})
        # only rows where every entrant has a prediction
        mask = df[list(cols.values())].notna().all(axis=1)
        t = M.score_table(df[mask], tgt, cols, mape=(tgt == "load_mw")); t["target"] = tgt; allm.append(t)
        unit = "MW" if tgt == "load_mw" else "$/MWh"
        L.append(f"\n## target `{tgt}` — MAE ({unit}), n={int(mask.sum())} hours\n")
        piv = t[t.split.isin(["all", "regime=normal", "spike+severe", "regime=severe", "ramp hours 17-21"])].pivot(index="split", columns="model", values="MAE").round(1)
        L.append(piv.loc[["all", "regime=normal", "spike+severe", "regime=severe", "ramp hours 17-21"]].to_markdown())
        L.append("\n\nRMSE / bias" + (" / MAPE" if tgt == "load_mw" else "") + ", all hours:\n")
        L.append(t[t.split == "all"].set_index("model")[["RMSE", "bias"] + (["MAPE"] if tgt == "load_mw" else [])].round(2).to_markdown())
        L.append("\n\nBy season (MAE):\n")
        L.append(t[t.split.str.startswith("season")].pivot(index="split", columns="model", values="MAE").round(1).to_markdown())
        if tgt == "load_mw":
            # by year, because the market and the training set both change
            rows = []
            for y, g in df[mask].groupby(df[mask].ts_local.dt.year):
                for name, col in cols.items():
                    rows.append({"year": y, "model": name, **M.score(g[tgt], g[col])})
            L.append("\n\nBy year (MAE):\n"); L.append(pd.DataFrame(rows).pivot(index="year", columns="model", values="MAE").round(1).to_markdown())
    # weather ablation (load only)
    abl = []
    for v in ["strict", "lenient", "observed"]:
        f = load_forecasts(v); f = f[(f.model == "gbm") & (f.target == "load_mw")]
        if f.empty:
            continue
        g = df[["ts_utc", "load_mw", "regime"]].merge(f[["ts_utc", "yhat"]], on="ts_utc")
        abl.append({"weather variant": v, **{k: round(v_, 1) for k, v_ in M.score(g.load_mw, g.yhat).items() if k != "n"}, "MAE spike+severe": round(M.score(g[g.regime != "normal"].load_mw, g[g.regime != "normal"].yhat)["MAE"], 1)})
    if abl:
        L.append("\n\n## Weather-input ablation (LightGBM, load)\n\nstrict = honest (no run after the origin); lenient = previous_day1 for all hours (up to 14 h fresher than allowed); observed = ERA5 (leakage ceiling).\n")
        L.append(pd.DataFrame(abl).set_index("weather variant").to_markdown())
    pd.concat(allm).to_csv(C.PROCESSED / "tournament_metrics.csv", index=False)
    (C.ROOT / "docs" / "scoreboard.md").write_text("\n".join(L))
    print("\n".join(L))


if __name__ == "__main__":
    main()
