"""Weather ingestion for the pilot site.

Sources (both real, public, no key needed):
  * NASA POWER hourly point API: irradiance, temperature, humidity, wind, rain (2016 onwards).
  * Open-Meteo historical forecast API: archived day-ahead forecasts from several NWP models.

Snapshots are written as parquet under services/data/snapshots/ so the proof pipeline
reproduces offline. Run: `uv run python -m sinchai_data.ingest`.
"""

from __future__ import annotations

import argparse
import time
from pathlib import Path

import httpx
import pandas as pd
from sinchai_schemas import constants as C

SNAP_DIR = Path(__file__).resolve().parents[1] / "snapshots"
NASA_URL = "https://power.larc.nasa.gov/api/temporal/hourly/point"
OM_HIST_FC_URL = "https://historical-forecast-api.open-meteo.com/v1/forecast"

NASA_PARAMS = [
    "ALLSKY_SFC_SW_DWN",  # GHI W/m2
    "CLRSKY_SFC_SW_DWN",  # clear-sky GHI W/m2
    "T2M",  # air temperature C
    "RH2M",  # relative humidity %
    "WS2M",  # wind speed at 2 m, m/s
    "PRECTOTCORR",  # precipitation mm/h
]
NASA_RENAME = {
    "ALLSKY_SFC_SW_DWN": "ghi",
    "CLRSKY_SFC_SW_DWN": "ghi_clear",
    "T2M": "temp_c",
    "RH2M": "rh",
    "WS2M": "wind_ms",
    "PRECTOTCORR": "rain_mm",
}
OM_MODELS = ["ecmwf_ifs025", "gfs_seamless", "icon_seamless"]
OM_VARS = ["shortwave_radiation", "cloud_cover", "temperature_2m", "precipitation"]
TZ = "Asia/Kolkata"


def _client() -> httpx.Client:
    return httpx.Client(timeout=120, headers={"User-Agent": "sinchaislot-data/0.1"})


def fetch_nasa_power(start_year: int, end_year: int) -> pd.DataFrame:
    lat, lon = C.get("site_lat"), C.get("site_lon")
    frames = []
    with _client() as cl:
        for year in range(start_year, end_year + 1):
            params = {
                "parameters": ",".join(NASA_PARAMS),
                "community": "RE",
                "latitude": lat,
                "longitude": lon,
                "start": f"{year}0101",
                "end": f"{year}1231",
                "format": "JSON",
                "time-standard": "UTC",
            }
            for attempt in range(4):
                r = cl.get(NASA_URL, params=params)
                if r.status_code == 200:
                    break
                time.sleep(5 * (attempt + 1))
            r.raise_for_status()
            p = r.json()["properties"]["parameter"]
            df = pd.DataFrame({k: pd.Series(v) for k, v in p.items()})
            df.index = pd.to_datetime(df.index, format="%Y%m%d%H", utc=True)
            frames.append(df)
            print(f"nasa power {year}: {len(df)} rows")
    out = pd.concat(frames).rename(columns=NASA_RENAME).sort_index()
    out = out.mask(out <= -999)  # NASA fill value
    out.index = out.index.tz_convert(TZ)
    out.index.name = "time"
    return out


def fetch_open_meteo_forecasts(start: str, end: str) -> pd.DataFrame:
    lat, lon = C.get("site_lat"), C.get("site_lon")
    frames = []
    months = pd.date_range(start, end, freq="MS")
    with _client() as cl:
        for m in months:
            m_end = min(m + pd.offsets.MonthEnd(0), pd.Timestamp(end))
            params = {
                "latitude": lat,
                "longitude": lon,
                "start_date": m.strftime("%Y-%m-%d"),
                "end_date": m_end.strftime("%Y-%m-%d"),
                "hourly": ",".join(OM_VARS),
                "models": ",".join(OM_MODELS),
                "timezone": TZ,
            }
            for attempt in range(4):
                r = cl.get(OM_HIST_FC_URL, params=params)
                if r.status_code == 200:
                    break
                time.sleep(5 * (attempt + 1))
            r.raise_for_status()
            h = r.json()["hourly"]
            df = pd.DataFrame(h)
            df["time"] = pd.to_datetime(df["time"]).dt.tz_localize(TZ, ambiguous="NaT", nonexistent="NaT")
            frames.append(df.set_index("time"))
            print(f"open-meteo forecasts {m:%Y-%m}: {len(df)} rows")
    return pd.concat(frames).sort_index()


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--nasa-start", type=int, default=2016)
    ap.add_argument("--nasa-end", type=int, default=2025)
    ap.add_argument("--om-start", default="2022-01-01")
    ap.add_argument("--om-end", default="2025-12-31")
    ap.add_argument("--skip-nasa", action="store_true")
    ap.add_argument("--skip-om", action="store_true")
    a = ap.parse_args()
    SNAP_DIR.mkdir(parents=True, exist_ok=True)
    if not a.skip_nasa:
        fetch_nasa_power(a.nasa_start, a.nasa_end).to_parquet(SNAP_DIR / "nasa_power_hourly.parquet")
    if not a.skip_om:
        fetch_open_meteo_forecasts(a.om_start, a.om_end).to_parquet(SNAP_DIR / "open_meteo_forecasts.parquet")


if __name__ == "__main__":
    main()
