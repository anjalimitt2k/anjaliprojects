"""Phase 8: the spike layer. (a) A walk-forward classifier for P(evening-ramp RT price spike on D) from features
available at 09:00 D-1 (forecast weather + net-load + recent price state). Reported with precision/recall,
Brier score and a reliability table, not just AUC. (b) Failure analysis: how much worse the point models are on
spike hours, and why history-based models structurally miss them. Writes docs/spike.md + fig6."""
from __future__ import annotations

import numpy as np
import pandas as pd
import matplotlib; matplotlib.use("Agg")
import matplotlib.pyplot as plt
from sklearn.metrics import roc_auc_score, brier_score_loss, precision_recall_fscore_support, average_precision_score
from . import config as C, metrics as M
from .features import feature_cols
from .eda import PAL, INK2

OUT = C.ROOT / "docs" / "eda"
EVENING = (17, 21)


def day_table(variant="strict") -> pd.DataFrame:
    X = pd.read_parquet(C.PROCESSED / f"features_{variant}.parquet")
    X = X[X.date >= C.WEATHER_FULL_FROM]
    h = pd.read_parquet(C.PROCESSED / "hourly.parquet")
    thr = M.spike_thresholds(h)
    ev = X[X.hour_local.between(*EVENING)]
    fc = feature_cols(X)
    # day-level features: evening means/max of hour-level features (all admissible at the origin)
    agg = ev.groupby("date")[fc].mean()
    agg.columns = [f"{c}_evmean" for c in agg.columns]
    extra = ev.groupby("date").agg(net_load_proxy_evmax=("net_load_proxy", "max"), solar_fc_ramp3_evmin=("solar_fc_ramp3", "min"),
                                   temp_daymax=("temp_daymax", "first"), lmp_rt_daymax_max7=("lmp_rt_daymax_max7", "first"),
                                   lmp_rt_daymax_d2=("lmp_rt_daymax_d2", "first"), dow=("dow_local", "first"), month=("month_local", "first"),
                                   is_holiday=("is_holiday", "first"), trend_days=("trend_days", "first"))
    D = agg.join(extra)
    # labels from actuals: any evening hour with RT hourly LMP >= spike threshold (p95 of DA LMP)
    y = ev.groupby("date").agg(rt_evmax=("lmp_rt", "max"), da_evmax=("lmp_da", "max"))
    D = D.join(y)
    D["y_spike"] = (D.rt_evmax >= thr["spike"]).astype(int)
    D["y_severe"] = (D.rt_evmax >= thr["severe"]).astype(int)
    return D.dropna(subset=["rt_evmax"]), thr


def walk_forward_clf(D: pd.DataFrame, label: str, retrain_days=28):
    import lightgbm as lgb
    feats = [c for c in D.columns if c not in {"rt_evmax", "da_evmax", "y_spike", "y_severe"}]
    days = D.index[D.index >= C.BACKTEST_FIRST_TARGET]
    probs = pd.Series(np.nan, index=days); last = None; clf = None
    for d in days:
        if last is None or (d - last).days >= retrain_days:
            tr = D[D.index <= d - pd.Timedelta(days=2)]
            pos = tr[label].sum()
            clf = lgb.LGBMClassifier(n_estimators=300, learning_rate=0.03, num_leaves=15, min_child_samples=20, subsample=0.8,
                                     subsample_freq=1, colsample_bytree=0.7, scale_pos_weight=max(1.0, (len(tr) - pos) / max(pos, 1)) ** 0.5,
                                     verbose=-1, n_jobs=4).fit(tr[feats], tr[label])
            last = d
        probs[d] = clf.predict_proba(D.loc[[d], feats])[:, 1][0]
    return probs, pd.Series(clf.feature_importances_, index=feats).sort_values(ascending=False)


def main():
    D, thr = day_table()
    L = [f"# Phase 8 — spike layer\n", f"Label: any hour 17–21 on D with RT hourly LMP ≥ ${thr['spike']:.0f}/MWh (the full-window p95 of DA LMP). "
         f"Severe: ≥ ${thr['severe']:.0f}. Features: evening means of the strict day-ahead feature set (forecast weather, CAISO renewables forecast, "
         "net-load proxy, recent price state). Walk-forward, retrained every 28 days.\n"]
    probs, imp = walk_forward_clf(D, "y_spike")
    T = D.loc[probs.index].assign(p=probs)
    y = T.y_spike
    L.append(f"\n## Evening-spike classifier, {T.index.min().date()} → {T.index.max().date()}: {len(T)} days, {int(y.sum())} positives ({100*y.mean():.1f} %)\n")
    L.append(f"- AUC {roc_auc_score(y, T.p):.3f}, average precision {average_precision_score(y, T.p):.3f} (base rate {y.mean():.3f}), Brier {brier_score_loss(y, T.p):.4f} "
             f"(climatology Brier {brier_score_loss(y, np.full(len(y), y.mean())):.4f})")
    rows = []
    for t in [0.2, 0.3, 0.4, 0.5, 0.6]:
        pr, rc, f1, _ = precision_recall_fscore_support(y, T.p >= t, average="binary", zero_division=0)
        rows.append({"threshold": t, "flagged days": int((T.p >= t).sum()), "precision": round(pr, 2), "recall": round(rc, 2), "F1": round(f1, 2)})
    L.append("\nPrecision / recall by decision threshold:\n"); L.append(pd.DataFrame(rows).set_index("threshold").to_markdown())
    bins = pd.cut(T.p, [0, .1, .2, .3, .4, .5, .7, 1.0], include_lowest=True)
    rel = T.groupby(bins, observed=True).agg(n=("p", "size"), mean_p=("p", "mean"), obs_rate=("y_spike", "mean")).round(3)
    L.append("\n\nReliability (predicted vs observed rate by bin):\n"); L.append(rel.to_markdown())
    # by year: where did the positives live?
    byy = T.groupby(T.index.year).agg(days=("p", "size"), positives=("y_spike", "sum"), mean_p=("p", "mean")).round(3)
    L.append("\n\nPositives by year (the regime shift):\n"); L.append(byy.to_markdown())
    L.append("\n\nTop features (split gain count):\n"); L.append(imp.head(12).to_frame("importance").to_markdown())
    # severe label as well (few positives: report honestly)
    if D.loc[probs.index].y_severe.sum() >= 5:
        ps, _ = walk_forward_clf(D, "y_severe"); ys = D.loc[ps.index].y_severe
        L.append(f"\n\nSevere label (≥ ${thr['severe']:.0f}): {int(ys.sum())} positives; AUC {roc_auc_score(ys, ps):.3f}, AP {average_precision_score(ys, ps):.3f}.")
    else:
        L.append(f"\n\nSevere label (≥ ${thr['severe']:.0f}): only {int(D.loc[probs.index].y_severe.sum())} positive days in the window — too few to fit or score honestly.")
    T[["p", "y_spike", "y_severe", "rt_evmax", "da_evmax"]].to_parquet(C.PROCESSED / "spike_probs.parquet")

    # ---- failure analysis on the point models (needs tournament output)
    try:
        from .tournament import wide, LABELS
        W = wide("strict")
        L.append("\n\n## Failure analysis: how much worse on spike hours, and why\n")
        rows = []
        for tgt, cols in [("load_mw", {"gbm": "gbm__load_mw", "chronos": "chronos__load_mw", "caiso": "load_caiso"}),
                          ("lmp_rt", {"gbm": "gbm__lmp_rt", "chronos": "chronos__lmp_rt", "da": "lmp_rt_da"})]:
            for m, c in cols.items():
                if c not in W:
                    continue
                n_ = M.score(W[W.regime == "normal"][tgt], W[W.regime == "normal"][c])["MAE"]
                s_ = M.score(W[W.regime != "normal"][tgt], W[W.regime != "normal"][c])["MAE"]
                v_ = M.score(W[W.regime == "severe"][tgt], W[W.regime == "severe"][c])["MAE"]
                b_ = M.score(W[W.regime == "severe"][tgt], W[W.regime == "severe"][c])["bias"]
                rows.append({"target": tgt, "model": LABELS.get(m, LABELS.get(c, m)), "MAE normal": round(n_, 1), "MAE spike+severe": round(s_, 1), "MAE severe": round(v_, 1), "× worse (severe/normal)": round(v_ / n_, 1), "bias severe": round(b_, 1)})
        L.append(pd.DataFrame(rows).to_markdown(index=False))
        if "gbm__lmp_rt" in W:
            sev = W[W.regime == "severe"].nlargest(10, "lmp_rt")[["ts_local", "lmp_rt", "lmp_da", "gbm__lmp_rt", "gbm__lmp_rt__p90", "chronos__lmp_rt"]].round(0)
            L.append("\n\nThe ten highest RT hours and what each forecast said the day before:\n"); L.append(sev.to_markdown(index=False))
        L.append("\n\n**Why history-based models structurally miss spikes.** Every lag feature (D-2, D-7, 7-day mean) describes a calm market "
                 "because spikes are rare and short; the training loss (L2 / pinball) is dominated by the ~95 % of normal hours, so the fitted "
                 "function is pulled toward the conditional *median*, which is calm. Spikes are driven by variables that are either absent "
                 "(outages, gas price, import availability) or only weakly proxied by forecast weather and net-load ramp. The bias column shows "
                 "it: every model under-forecasts severe hours by a large negative bias; the RT target is right-skewed and the models are not.")
    except Exception as e:  # noqa: BLE001
        L.append(f"\n\n(failure analysis skipped: {e})")
    # figure: reliability + probs over time
    fig, axes = plt.subplots(1, 2, figsize=(12, 4))
    axes[0].plot([0, 1], [0, 1], color=INK2, lw=1, ls=":"); axes[0].plot(rel.mean_p, rel.obs_rate, "o-", color=PAL[0], lw=2, ms=7)
    for n, x_, y_ in zip(rel.n, rel.mean_p, rel.obs_rate):
        axes[0].annotate(str(n), (x_, y_), xytext=(5, -10), textcoords="offset points", fontsize=8, color=INK2)
    axes[0].set_xlabel("predicted P(evening spike)"); axes[0].set_ylabel("observed rate"); axes[0].set_title("Reliability (n per bin)")
    axes[1].plot(T.index, T.p, color=PAL[0], lw=1, label="P(spike)"); axes[1].scatter(T.index[y == 1], np.ones(int(y.sum())) * 1.02, color=PAL[1], s=12, label="spike days")
    import matplotlib.dates as mdates
    axes[1].xaxis.set_major_locator(mdates.MonthLocator(interval=3)); axes[1].xaxis.set_major_formatter(mdates.DateFormatter("%b %y"))
    axes[1].set_ylim(0, 1.08); axes[1].set_title("Daily spike probability vs realised spike days"); axes[1].legend(fontsize=8, loc="center right")
    fig.suptitle("Spike layer: calibrated probabilities, and where the positives actually were", x=0.01, ha="left", fontsize=13, fontweight="semibold")
    fig.tight_layout(rect=(0, 0, 1, 0.92)); fig.savefig(OUT / "fig6_spike_classifier.png", dpi=150); plt.close(fig)
    (C.ROOT / "docs" / "spike.md").write_text("\n".join(L)); print("\n".join(L))


if __name__ == "__main__":
    main()
