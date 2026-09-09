"""Phase 1: pull raw CAISO + weather sources, cache them, join onto one tidy hourly index.

Design rules (see docs/data_notes.md for the *why* behind each):
  * Canonical index is UTC hourly (`ts_utc`). Local-clock columns are derived, never the key.
    Joining on UTC is what makes DST transition days come out right (23h / 25h local days).
  * Every source is cached to data/raw/<name>.parquet and re-pulled only if the cache is missing.
  * Nothing in here does imputation silently: gaps are left as NaN and reported by validate.py;
    the one known structural gap (fall-back 01:00 PST hour in the Outlook demand feed) is
    imputed in build_hourly() and flagged with `load_imputed=True`.
"""
from __future__ import annotations

import logging
import time

import pandas as pd
import requests

from . import config as C

log = logging.getLogger(__name__)


def _caiso():
    import socket
    socket.setdefaulttimeout(120)  # OASIS occasionally never answers; without this a pull hangs forever
    import truststore  # corporate proxy injects its own CA; use the OS trust store
    truststore.inject_into_ssl()
    import gridstatus
    return gridstatus.CAISO()


def _oasis_chunked(name: str, fetch, days: int = 28, expect_per_day: int | None = None) -> pd.DataFrame:
    """Pull an OASIS series in local-midnight-aligned chunks of <= `days`, with retries.

    Why not gridstatus's own 31-day chunker: it derives chunk boundaries from the (PDT) start time,
    so once the window crosses into PST every chunk starts at 23:00 the day before and spans 31d+1h.
    OASIS silently rejects those ("No data found") and we lost ~280 winter days per source that way.
    `fetch(start_ts, end_ts)` receives tz-aware local timestamps; end is exclusive.
    """
    lo = pd.Timestamp(C.START, tz=C.TZ)
    hi = pd.Timestamp(C.END, tz=C.TZ) + pd.Timedelta(days=1)
    frames = []
    edges = list(pd.date_range(lo, hi, freq=f"{days}D")) + [hi]
    for a, b in zip(edges[:-1], edges[1:]):
        if a >= b:
            continue
        for attempt in range(5):
            try:
                df = fetch(a, b)
                if df is None or len(df) == 0:
                    raise RuntimeError("empty result")
                break
            except Exception as e:  # noqa: BLE001
                log.warning("%s chunk %s..%s attempt %d failed: %s", name, a.date(), b.date(), attempt + 1, str(e)[:120])
                time.sleep(15 * (attempt + 1))
        else:
            raise RuntimeError(f"{name}: chunk {a.date()}..{b.date()} failed 5 times")
        if expect_per_day:
            n_days = (b - a).days
            got = df["Interval Start"].nunique()
            if got < 0.95 * expect_per_day * n_days:
                log.warning("%s chunk %s..%s looks short: %d intervals for %d days", name, a.date(), b.date(), got, n_days)
        frames.append(df)
        log.info("%s chunk %s..%s ok (%d rows)", name, a.date(), b.date(), len(df))
    out = pd.concat(frames, ignore_index=True)
    return out.drop_duplicates()


def _cached(name: str, fn):
    path = C.RAW / f"{name}.parquet"
    if path.exists():
        log.info("cache hit  %s", name)
        return pd.read_parquet(path)
    log.info("pulling    %s ...", name)
    t = time.time()
    df = fn()
    df.to_parquet(path, index=False)
    log.info("saved      %s  rows=%d  %.0fs", name, len(df), time.time() - t)
    return df


def _utc_hour(s: pd.Series) -> pd.Series:
    """Tz-aware Pacific timestamps -> UTC, floored to the hour."""
    return pd.to_datetime(s).dt.tz_convert("UTC").dt.floor("h")


# ---------------------------------------------------------------- raw pulls
def pull_load_5min() -> pd.DataFrame:
    """CAISO 'Today's Outlook' demand, 5-min. This is the quantity CAISO's demand forecast targets.
    NOTE: SLD_FCST market_run_id=ACTUAL (gridstatus get_load_hourly) is a *different* series that
    runs up to ~6.5 GW above this midday; do not use it as the actual. See docs/data_notes.md."""
    c = _caiso()
    return c.get_load(C.START, end=pd.Timestamp(C.END) + pd.Timedelta(days=1))[["Interval Start", "Load"]]


def pull_fuel_mix_5min() -> pd.DataFrame:
    """CAISO Today's Outlook fuelsource.csv, 5-min. Fleet-total solar/wind; this is what CAISO's own
    'net demand' curve subtracts. OASIS SLD_REN_FCST ACTUAL runs ~15% lower (narrower scope) and has
    occasional hour dropouts, but it is the consistent pair for the OASIS DA renewables *forecast*."""
    c = _caiso()
    df = c.get_fuel_mix(C.START, end=pd.Timestamp(C.END) + pd.Timedelta(days=1))
    return df[["Interval Start", "Solar", "Wind"]]


def pull_load_fc_da() -> pd.DataFrame:
    c = _caiso()
    def f(a, b):
        df = c.get_load_forecast_day_ahead(a, end=b)
        return df[df["TAC Area Name"] == C.LOAD_AREA][["Interval Start", "Publish Time", "Load Forecast"]]
    return _oasis_chunked("load_fc_da", f, expect_per_day=24)


def pull_lmp_da() -> pd.DataFrame:
    c = _caiso()
    def f(a, b):
        df = c.get_lmp(a, end=b, market="DAY_AHEAD_HOURLY", locations=[C.HUB])
        return df[["Interval Start", "LMP", "Energy", "Congestion", "Loss"]]
    return _oasis_chunked("lmp_da", f, expect_per_day=24)


def pull_lmp_rt15() -> pd.DataFrame:
    c = _caiso()
    def f(a, b):
        df = c.get_lmp(a, end=b, market="REAL_TIME_15_MIN", locations=[C.HUB])
        return df[["Interval Start", "LMP"]]
    return _oasis_chunked("lmp_rt15", f, expect_per_day=96)


def pull_ren_hourly() -> pd.DataFrame:
    c = _caiso()
    def f(a, b):
        df = c.get_renewables_hourly(a, end=b)
        return df[df["Location"].isin(["CAISO", C.ZONE])][["Interval Start", "Location", "Solar", "Wind"]]
    return _oasis_chunked("ren_hourly", f, expect_per_day=24)


def pull_ren_fc_dam() -> pd.DataFrame:
    c = _caiso()
    def f(a, b):
        df = c.get_renewables_forecast_dam(a, end=b)
        return df[df["Location"].isin(["CAISO", C.ZONE])][["Interval Start", "Publish Time", "Location", "Solar MW", "Wind MW"]]
    return _oasis_chunked("ren_fc_dam", f, expect_per_day=24)


def pull_weather() -> pd.DataFrame:
    """Open-Meteo previous-runs API, UTC, one row per (point, hour). Chunked by calendar year."""
    import truststore; truststore.inject_into_ssl()
    url = "https://previous-runs-api.open-meteo.com/v1/forecast"
    hourly = ",".join(f"{v}_previous_day1" for v in C.WEATHER_VARS)
    frames = []
    # pad one day each side: local window edges fall inside UTC days
    start = pd.Timestamp(C.START) - pd.Timedelta(days=1)
    end = pd.Timestamp(C.END) + pd.Timedelta(days=2)
    for name, (lat, lon) in C.WEATHER_POINTS.items():
        for y0 in pd.date_range(start, end, freq="YS").union([start]):
            y1 = min(pd.Timestamp(year=y0.year, month=12, day=31), end)
            if y0 > end:
                continue
            p = dict(latitude=lat, longitude=lon, start_date=y0.strftime("%Y-%m-%d"), end_date=y1.strftime("%Y-%m-%d"),
                     hourly=hourly, timezone="UTC", models="best_match", wind_speed_unit="ms")
            for attempt in range(5):
                r = requests.get(url, params=p, timeout=120)
                if r.status_code == 200:
                    break
                log.warning("open-meteo %s %s -> %s %s", name, y0.year, r.status_code, r.text[:120])
                time.sleep(10 * (attempt + 1))
            r.raise_for_status()
            h = pd.DataFrame(r.json()["hourly"])
            h.columns = [c_.replace("_previous_day1", "") for c_ in h.columns]
            h["ts_utc"] = pd.to_datetime(h.pop("time"), utc=True)
            h["point"] = name
            frames.append(h)
            time.sleep(1)
    return pd.concat(frames, ignore_index=True)


SOURCES = {
    "load_5min": pull_load_5min,
    "fuel_mix_5min": pull_fuel_mix_5min,
    "load_fc_da": pull_load_fc_da,
    "lmp_da": pull_lmp_da,
    "lmp_rt15": pull_lmp_rt15,
    "ren_hourly": pull_ren_hourly,
    "ren_fc_dam": pull_ren_fc_dam,
    "weather": pull_weather,
}


def pull_all(only: list[str] | None = None) -> dict[str, pd.DataFrame]:
    return {k: _cached(k, fn) for k, fn in SOURCES.items() if not only or k in only}


# ---------------------------------------------------------------- tidy join
def build_hourly(raw: dict[str, pd.DataFrame] | None = None) -> pd.DataFrame:
    raw = raw or pull_all()

    # canonical UTC hourly index covering the local window exactly
    lo = pd.Timestamp(C.START, tz=C.TZ).tz_convert("UTC")
    hi = (pd.Timestamp(C.END, tz=C.TZ) + pd.Timedelta(days=1)).tz_convert("UTC") - pd.Timedelta(hours=1)
    idx = pd.date_range(lo, hi, freq="h", name="ts_utc")
    out = pd.DataFrame(index=idx)

    # --- load actual: hourly mean of 5-min Outlook demand (needs >=6 of 12 intervals)
    l5 = raw["load_5min"].copy()
    l5["ts_utc"] = _utc_hour(l5["Interval Start"])
    g = l5.groupby("ts_utc")["Load"]
    load = g.mean().where(g.count() >= 6)
    out["load_mw"] = load
    out["load_n5min"] = g.count()

    # --- CAISO official day-ahead load forecast (publish time kept: proves it was day-ahead)
    f = raw["load_fc_da"].copy()
    f["ts_utc"] = _utc_hour(f["Interval Start"])
    f = f.sort_values("Publish Time").groupby("ts_utc").last()   # if ever re-published, keep latest DA run
    out["load_fc_caiso_mw"] = f["Load Forecast"]
    out["load_fc_publish_utc"] = pd.to_datetime(f["Publish Time"]).dt.tz_convert("UTC")

    # --- prices
    da = raw["lmp_da"].copy(); da["ts_utc"] = _utc_hour(da["Interval Start"])
    da = da.groupby("ts_utc").mean(numeric_only=True)
    out["lmp_da"] = da["LMP"]; out["lmp_da_energy"] = da["Energy"]
    out["lmp_da_congestion"] = da["Congestion"]; out["lmp_da_loss"] = da["Loss"]

    rt = raw["lmp_rt15"].copy(); rt["ts_utc"] = _utc_hour(rt["Interval Start"])
    g = rt.groupby("ts_utc")["LMP"]
    out["lmp_rt"] = g.mean().where(g.count() >= 2)
    out["lmp_rt_max15"] = g.max(); out["lmp_rt_min15"] = g.min(); out["lmp_rt_n15"] = g.count()

    # --- renewables actual + DA forecast, system and zone
    rh = raw["ren_hourly"].copy(); rh["ts_utc"] = _utc_hour(rh["Interval Start"])
    for loc, tag in [("CAISO", "sys"), (C.ZONE, "zone")]:
        s = rh[rh["Location"] == loc].groupby("ts_utc")[["Solar", "Wind"]].mean()
        out[f"solar_{tag}_mw"] = s["Solar"]; out[f"wind_{tag}_mw"] = s["Wind"]
    rf = raw["ren_fc_dam"].copy(); rf["ts_utc"] = _utc_hour(rf["Interval Start"])
    for loc, tag in [("CAISO", "sys"), (C.ZONE, "zone")]:
        s = rf[rf["Location"] == loc].sort_values("Publish Time").groupby("ts_utc")[["Solar MW", "Wind MW"]].last()
        out[f"solar_fc_{tag}_mw"] = s["Solar MW"]; out[f"wind_fc_{tag}_mw"] = s["Wind MW"]

    # --- Outlook fleet-total renewables (same feed family as load_mw)
    fm = raw["fuel_mix_5min"].copy(); fm["ts_utc"] = _utc_hour(fm["Interval Start"])
    g = fm.groupby("ts_utc")[["Solar", "Wind"]]
    ok = g.count()["Solar"] >= 6
    out["solar_outlook_mw"] = g.mean()["Solar"].where(ok)
    out["wind_outlook_mw"] = g.mean()["Wind"].where(ok)

    # --- weather (day-before forecast), wide: <var>_<point>
    w = raw["weather"].pivot(index="ts_utc", columns="point")
    # Open-Meteo radiation/precipitation are *preceding-hour* means/sums (value at 12:00 covers 11:00-12:00).
    # CAISO uses interval-start (12:00 covers 12:00-13:00). Shift those variables back one hour so every
    # column in this frame means "the interval starting at ts_utc". Confirmed empirically: corr(solar,
    # shortwave) peaks at a -1h shift before this fix and at 0 after.
    preceding = [v for v in C.WEATHER_VARS if "radiation" in v or v == "precipitation"]
    for v in preceding:
        w[v] = w[v].shift(-1)
    w.columns = [f"{v}_{p}" for v, p in w.columns]
    out = out.join(w)

    # --- known structural gap: Outlook feeds omit the repeated 01:00 PST hour on fall-back days
    out["load_imputed"] = out["load_mw"].isna()
    for col in ["load_mw", "solar_outlook_mw", "wind_outlook_mw"]:
        out[col] = out[col].interpolate(limit=1, limit_area="inside")
    out["load_imputed"] &= out["load_mw"].notna()

    # --- first-class derived columns
    # net load = CAISO's own "net demand" definition: Outlook demand minus Outlook fleet solar + wind
    out["net_load_mw"] = out["load_mw"] - out["solar_outlook_mw"] - out["wind_outlook_mw"]
    # OASIS-scope variant: the actual that pairs with the OASIS DA renewables forecast
    out["net_load_oasis_mw"] = out["load_mw"] - out["solar_sys_mw"] - out["wind_sys_mw"]
    out["net_load_fc_caiso_mw"] = out["load_fc_caiso_mw"] - out["solar_fc_sys_mw"] - out["wind_fc_sys_mw"]
    out["da_rt_spread"] = out["lmp_da"] - out["lmp_rt"]

    # --- local clock columns (derived from UTC, never the key)
    loc = out.index.tz_convert(C.TZ)
    out["ts_local"] = loc
    out["date_local"] = loc.date.astype(str)
    out["hour_local"] = loc.hour
    out["dow_local"] = loc.dayofweek
    out["month_local"] = loc.month
    out["is_dst"] = [bool(t.dst()) for t in loc]

    return out.reset_index()


def save_hourly(df: pd.DataFrame) -> None:
    C.PROCESSED.mkdir(parents=True, exist_ok=True)
    df.to_parquet(C.PROCESSED / "hourly.parquet", index=False)
