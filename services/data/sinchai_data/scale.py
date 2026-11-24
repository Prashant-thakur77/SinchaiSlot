"""Sun, pumping potential and crop water need for candidate rollout districts.

Run: python -m sinchai_data.scale   (downloads NASA POWER hourly 2024-2025, no key)
Writes reports/scale.json. Points are district headquarters, approximate.
"""

from __future__ import annotations

import json
import time

import httpx
import pandas as pd
from sinchai_devices.physics import PVArray, default_pump
from sinchai_planner import fao56
from sinchai_schemas import constants as C

from .ingest import NASA_PARAMS, NASA_RENAME, NASA_URL, SNAP_DIR, TZ

DISTRICTS = {
    "Samastipur": ("Bihar", 25.86, 85.78), "Vaishali": ("Bihar", 25.69, 85.21), "Muzaffarpur": ("Bihar", 26.12, 85.39),
    "Darbhanga": ("Bihar", 26.15, 85.90), "Madhubani": ("Bihar", 26.35, 86.07), "Purnia": ("Bihar", 25.78, 87.47),
    "Nalanda": ("Bihar", 25.20, 85.52), "Gaya": ("Bihar", 24.79, 85.00),
    "Gorakhpur": ("Uttar Pradesh", 26.76, 83.37), "Ranchi": ("Jharkhand", 23.34, 85.31),
    "Cooch Behar": ("West Bengal", 26.32, 89.45), "Kalahandi": ("Odisha", 19.91, 83.16),
    "Raipur": ("Chhattisgarh", 21.25, 81.63), "Nagaon": ("Assam", 26.35, 92.68),
}
REPORT = SNAP_DIR.parents[2] / "reports" / "scale.json"


def fetch(lat: float, lon: float, years: tuple[int, ...] = (2024, 2025)) -> tuple[pd.DataFrame, float]:
    frames, elev = [], 0.0
    with httpx.Client(timeout=120, headers={"User-Agent": "sinchaislot-data/0.1"}) as cl:
        for y in years:
            for attempt in range(4):
                try:
                    r = cl.get(NASA_URL, params={"parameters": ",".join(NASA_PARAMS), "community": "RE", "latitude": lat,
                                                 "longitude": lon, "start": f"{y}0101", "end": f"{y}1231",
                                                 "format": "JSON", "time-standard": "UTC"})
                    if r.status_code == 200:
                        break
                except httpx.TransportError:
                    if attempt == 3:
                        raise
                time.sleep(5 * (attempt + 1))
            r.raise_for_status()
            j = r.json()
            elev = float(j["geometry"]["coordinates"][2])
            f = pd.DataFrame({k: pd.Series(v) for k, v in j["properties"]["parameter"].items()})
            f.index = pd.to_datetime(f.index, format="%Y%m%d%H", utc=True)
            frames.append(f)
    out = pd.concat(frames).rename(columns=NASA_RENAME).sort_index()
    out = out.mask(out <= -999)
    out.index = out.index.tz_convert(TZ)
    return out, elev


def district(name: str, state: str, lat: float, lon: float) -> dict:
    obs, elev = fetch(lat, lon)
    arr = PVArray(C.get("pv_kwp"), lat, lon, derate=C.get("pv_system_derate"), temp_coeff=C.get("pv_temp_coeff_per_c"))
    pump = default_pump()
    pv = arr.dc_power_kw(obs["ghi"].fillna(0), obs["temp_c"].ffill(), obs["wind_ms"].ffill())
    water = pd.Series(pump.flow_for_power(pv.to_numpy()), index=pv.index)
    years = len(pv) / 8766
    daily = fao56.add_et0(fao56.daily_weather_from_hourly(obs), lat, elev)
    crops = {}
    for k, crop in fao56.CROPS.items():
        ev = fao56.simulate_plot(crop, daily, 2024)
        crops[k] = {"name": crop.name_en, "irrigations": len(ev),
                    "gross_m3_per_acre": round(sum(fao56.gross_m3(e.net_mm, 0.404686, C.get("application_efficiency")) for e in ev))}
    return {"name": name, "state": state, "lat": lat, "lon": lon, "elevation_m": round(elev),
            "pv_kwh_per_kwp": round(float(pv.sum()) / years / arr.kwp),
            "pump_m3_per_year_if_always_on": round(float(water.sum()) / years),
            "pv_kwh_per_kwp_by_month": [round(float(v)) for v in (pv.groupby(pv.index.month).sum() / years / arr.kwp)],
            "rain_mm": round(float(obs["rain_mm"].sum()) / years), "crops": crops}


def main() -> None:
    rows = []
    for n, (st, lat, lon) in DISTRICTS.items():
        rows.append(district(n, st, lat, lon))
        print(rows[-1]["name"], rows[-1]["pv_kwh_per_kwp"], rows[-1]["pump_m3_per_year_if_always_on"], flush=True)
    REPORT.write_text(json.dumps({"generated_by": "python -m sinchai_data.scale", "years": [2024, 2025],
                                  "label": "REAL: NASA POWER hourly sun and weather at the district headquarters point. "
                                           "DERIVED: panel output, pump flow (Samastipur head) and FAO-56 crop need",
                                  "districts": rows}, indent=1))


if __name__ == "__main__":
    main()
