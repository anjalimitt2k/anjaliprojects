"""Phase 4: leak-free features. One row per target hour; every feature is computable at the origin,
09:00 local on D-1 (config.ORIGIN_HOUR_LOCAL). See docs/features.md for the note per feature.

Weather variants (the leakage ablation):
  strict  : target hours 00-09 of D use previous_day1 (run >= 24 h before valid, i.e. before the origin);
            hours 10-23 use previous_day2 (48 h), because the day1 run for those hours is initialised after 09:00 D-1.
  lenient : previous_day1 for every hour (up to 14 h of weather-model updates the operator would not have had).
  observed: ERA5 reanalysis (pure leakage; the "what would perfect weather be worth" ceiling).
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import holidays
from . import config as C

WX_POINTS = list(C.WEATHER_POINTS)
WX_VARS = ["temperature_2m", "apparent_temperature", "relative_humidity_2m", "wind_speed_10m", "cloud_cover",
           "shortwave_radiation", "precipitation"]
TARGETS = ["load_mw", "lmp_rt", "lmp_da"]


def _by_date_hour(df: pd.DataFrame, col: str) -> pd.DataFrame:
    """date_local x hour_local matrix (fall-back duplicate hour averaged)."""
    return df.pivot_table(index="date_local", columns="hour_local", values=col, aggfunc="mean")


def build(df: pd.DataFrame, weather: str = "strict") -> pd.DataFrame:
    df = df.sort_values("ts_utc").reset_index(drop=True)
    X = df[["ts_utc", "ts_local", "date_local", "hour_local", "dow_local", "month_local", "is_dst"] + TARGETS].copy()
    X["date"] = pd.to_datetime(X.date_local)

    # ---- calendar (known for any future date; no leak)
    X["is_weekend"] = (X.dow_local >= 5).astype(int)
    hol = holidays.US(state="CA", years=range(2023, 2028))
    X["is_holiday"] = X.date.dt.date.map(lambda d: int(d in hol))
    X["doy_sin"] = np.sin(2 * np.pi * X.date.dt.dayofyear / 365.25)
    X["doy_cos"] = np.cos(2 * np.pi * X.date.dt.dayofyear / 365.25)
    X["hour_sin"] = np.sin(2 * np.pi * X.hour_local / 24)
    X["hour_cos"] = np.cos(2 * np.pi * X.hour_local / 24)
    X["trend_days"] = (X.date - pd.Timestamp(C.START)).dt.days  # lets trees split by era (non-stationary duck)
    # daylight proxy: astronomical day length at 36N (hours), no data needed
    decl = 23.44 * np.sin(2 * np.pi * (284 + X.date.dt.dayofyear) / 365)
    X["daylight_h"] = 24 / np.pi * np.arccos(-np.tan(np.radians(36)) * np.tan(np.radians(decl)))

    # ---- lags on the UTC index: 48 h and 168 h before the target are complete at 09:00 D-1
    s = df.set_index("ts_utc")
    for tgt in TARGETS:
        for lag in (48, 168, 336):
            X[f"{tgt}_lag{lag}"] = s[tgt].shift(lag).values
    X["net_load_lag48"] = s.net_load_mw.shift(48).values
    X["net_load_lag168"] = s.net_load_mw.shift(168).values

    # ---- as-of-origin aggregates keyed by target date D (origin = D-1 09:00 local)
    byd = X.groupby("date").size().index
    # D-1 hours 00-08 are observed at the origin
    early = df[df.hour_local <= 8].groupby("date_local").agg(load_d1_early_mean=("load_mw", "mean"), load_d1_h8=("load_mw", "last"),
                                                              lmp_rt_d1_early_mean=("lmp_rt", "mean"), lmp_rt_d1_early_max=("lmp_rt", "max"))
    early.index = pd.to_datetime(early.index) + pd.Timedelta(days=1)          # value for D-1 -> feature of D
    X = X.merge(early, left_on="date", right_index=True, how="left")
    # last complete day D-2 and rolling 7 complete days (D-8..D-2), per target hour
    for tgt, name in [("load_mw", "load"), ("lmp_rt", "lmp_rt"), ("net_load_mw", "net_load")]:
        P = _by_date_hour(df, tgt); P.index = pd.to_datetime(P.index)
        roll7 = P.rolling(7, min_periods=5).mean().shift(2)                     # ends at D-2
        roll7.index.name = "date"
        lk = roll7.stack().rename(f"{name}_h_mean7").reset_index().rename(columns={"level_1": "hour_local"})
        X = X.merge(lk, on=["date", "hour_local"], how="left")
        if tgt == "load_mw":
            dmax = P.max(axis=1); X[f"{name}_daymax_d2"] = X.date.map(dmax.shift(2, freq="D"))
            X[f"{name}_daymax_mean7"] = X.date.map(dmax.rolling(7, min_periods=5).mean().shift(2, freq="D"))
        if tgt == "lmp_rt":
            dmax = P.max(axis=1); X["lmp_rt_daymax_d2"] = X.date.map(dmax.shift(2, freq="D"))
            X["lmp_rt_daymax_max7"] = X.date.map(dmax.rolling(7, min_periods=5).max().shift(2, freq="D"))
    # CAISO's DA forecast for D-1 (published D-2 ~09:10) and CAISO's realised error on D-2
    Pf = _by_date_hour(df, "load_fc_caiso_mw"); Pf.index = pd.to_datetime(Pf.index)
    Pa = _by_date_hour(df, "load_mw"); Pa.index = pd.to_datetime(Pa.index)
    lk = Pf.shift(1).stack().rename("caiso_fc_d1_samehour").reset_index().rename(columns={"level_1": "hour_local", "date_local": "date"})
    X = X.merge(lk, on=["date", "hour_local"], how="left")
    err = (Pa - Pf).shift(2); err.index.name = "date"
    lk = err.stack().rename("caiso_err_d2_samehour").reset_index().rename(columns={"level_1": "hour_local"})
    X = X.merge(lk, on=["date", "hour_local"], how="left")
    # DA LMP for D-1 (published ~13:00 D-2) is known at the origin
    Pd = _by_date_hour(df, "lmp_da"); Pd.index = pd.to_datetime(Pd.index); Pd.index.name = "date"
    lk = Pd.shift(1).stack().rename("lmp_da_d1_samehour").reset_index().rename(columns={"level_1": "hour_local"})
    X = X.merge(lk, on=["date", "hour_local"], how="left")

    # ---- CAISO's DA renewables forecast for D: published ~07:00 D-1, i.e. before the origin
    X["solar_fc_mw"] = df.solar_fc_sys_mw.values
    X["wind_fc_mw"] = df.wind_fc_sys_mw.values
    sfc = pd.Series(df.solar_fc_sys_mw.values, index=df.ts_utc)
    X["solar_fc_ramp3"] = (sfc - sfc.shift(3)).values                        # negative = sunset ramp
    X["solar_fc_daymax"] = X.date.map(df.groupby("date_local").solar_fc_sys_mw.max().rename(index=pd.to_datetime))
    # forecast net-load proxy: last week's load at this hour minus tomorrow's renewables forecast
    X["net_load_proxy"] = X.load_mw_lag168 - X.solar_fc_mw - X.wind_fc_mw
    X["net_load_proxy_ramp3"] = X.net_load_proxy - X.net_load_proxy.shift(3)   # consecutive UTC hours; D-1 values known

    # ---- weather for the target hour, by variant
    suf = {"strict": None, "lenient": "", "observed": "_obs"}[weather]
    for v in WX_VARS:
        for pt in WX_POINTS:
            if weather == "strict":
                d1, d2 = df[f"{v}_{pt}"], df[f"{v}_{pt}_d2"]
                X[f"{v}_{pt}"] = np.where(df.hour_local <= C.ORIGIN_HOUR_LOCAL, d1, d2)
            else:
                X[f"{v}_{pt}"] = df[f"{v}_{pt}{suf}"].values
    temps = [f"temperature_2m_{pt}" for pt in WX_POINTS]
    X["temp_mean6"] = X[temps].mean(axis=1)
    X["temp_socal"] = X[["temperature_2m_la", "temperature_2m_riv", "temperature_2m_sd"]].mean(axis=1)
    X["cdh_socal"] = (X.temp_socal - 20).clip(lower=0)                        # cooling-degree-hours proxy
    g = X.groupby("date")
    X["temp_daymax"] = g.temp_mean6.transform("max"); X["temp_daymin"] = g.temp_mean6.transform("min")
    X["temp_daymax_d1"] = X.date.map(g.temp_mean6.max().shift(1, freq="D"))   # yesterday's forecast max (heat persistence)
    X["sw_fres_ramp3"] = X.shortwave_radiation_fres - X.shortwave_radiation_fres.shift(3)
    X["weather_variant"] = weather
    return X


FEATURE_EXCLUDE = {"ts_utc", "ts_local", "date_local", "date", "weather_variant", *TARGETS}


def feature_cols(X: pd.DataFrame) -> list[str]:
    return [c for c in X.columns if c not in FEATURE_EXCLUDE]


def main():
    df = pd.read_parquet(C.PROCESSED / "hourly.parquet")
    for variant in ["strict", "lenient", "observed"]:
        X = build(df, variant)
        X.to_parquet(C.PROCESSED / f"features_{variant}.parquet", index=False)
        print(variant, X.shape, "features:", len(feature_cols(X)))
    X = build(df, "strict")
    fc = feature_cols(X)
    bt = X[X.date >= C.WEATHER_FULL_FROM]
    print("\nmissing per feature (from", C.WEATHER_FULL_FROM, ") > 1%:")
    miss = bt[fc].isna().mean().sort_values(ascending=False)
    print(miss[miss > 0.01].round(3).to_string() or "none")


if __name__ == "__main__":
    main()
