# Data and labels

| Data | Source | Label |
|---|---|---|
| Hourly irradiance, temperature, humidity, wind, rain, Samastipur 2016-2025 | NASA POWER (`services/data/snapshots/nasa_power_hourly.parquet`) | REAL |
| Archived NWP forecasts (ECMWF IFS 0.25, GFS, ICON), 2022-2025 | Open-Meteo historical forecast API (`open_meteo_forecasts.parquet`) | REAL |
| Crop coefficients, stage lengths, soil water | FAO-56 tables | PUBLISHED |
| Prices, emission factor, capex, subsidy rules, context statistics | constants.yaml with source URLs | PUBLISHED |
| Pump, PV derate, village loads, tariffs, budget depth | constants.yaml `kind: assumption` | ASSUMPTION |
| Village (50 households, 51 plots, tenancy, crops), bookings | Prayogshala generator | SIMULATED |
| Drive and pump telemetry | Altivar model on the verified register map | SIMULATED |
| Ledger history | policy D run on the synthetic village over real 2024 weather | SIMULATED |
| Agent eval utterances | written for the eval (dev/test split) | SAMPLE |

Forecast training 2022-2023, held-out testing 2024-2025 (docs/decisions/0002). Field geometry in the
Village Twin is a schematic mosaic, not surveyed boundaries.

## Sentinel-2 crop-calendar map (REAL imagery, DERIVED classes)

`services/data/sinchai_data/sentinel.py` (run `env -u VIRTUAL_ENV uv run python -m sinchai_data.sentinel`;
`--offline` reclassifies the committed stack without network; `--lat/--lon` re-centres the AOI).

| Item | Detail |
|---|---|
| Imagery | Sentinel-2 L2A, Earth Search STAC v1, collection `sentinel-2-c1-l2a`, tile MGRS 45RUJ, public COGs read by HTTP range requests (no key) |
| AOI | 2.5 x 2.5 km centred on `site_lat`/`site_lon` (25.86 N, 85.78 E), UTM 45N, 10 m grid (250 x 250 px) |
| Period | 2024-06-01 to 2025-05-31: 64 candidate dates, 30 used (5 clear looks in the Aug-Oct kharif peak window, 8 in the Dec 15-Mar 15 rabi window) |
| Mask | SCL classes 4, 5, 6 kept; a scene is used when at least 60 % of the AOI is clear; outside the monsoon the clearest scene per 10 days |
| Classes | Phenology rules on per-pixel NDVI (kharif peak, rabi peak, inter-season trough, whole-year percentiles) plus median NDWI for water; rules and thresholds are written into the snapshot JSON |
| Validation | **Not validated against field labels.** No ground-truth crop labels are available offline, and no citable district crop-area table was found to compare against |

Files:

| File | Content | Label |
|---|---|---|
| `services/data/snapshots/s2_ndvi_stack.npz` | NDVI stack (int16, x1e4, -32768 = masked), dates, scene ids, UTM bounds, median NDWI | REAL (derived index) |
| `services/data/snapshots/s2_crop_shares.json` | class shares and hectares, scene list with tile cloud % and AOI clear %, method, crop-mix mapping | DERIVED |
| `apps/web/public/basemap/samastipur_s2_truecolor.png` + `.json` | true colour (B04/B03/B02) of 2025-01-26, warped to lon/lat; bounds in the JSON | REAL |
| `apps/web/public/basemap/samastipur_s2_crops.png` + `.json` | class overlay (transparent background) with legend and bounds | DERIVED |

Class shares for the site AOI (2024-25): kharif only 7.4 %, rabi only 0.1 %, double cropped 4.0 %,
orchard/trees 6.6 %, fallow/built-up 35.2 %, water 1.8 %, other/mixed 44.9 %.

**Caveat: the configured site point falls on Samastipur town.** The AOI is mostly built-up, the
Burhi Gandak river and town trees; only 11.5 % of it is cropland by these rules. Vacant urban plots
that green up in the monsoon can pass as kharif-only, and mixed town pixels end up in other/mixed.
These shares describe the town AOI, not a farming village. Re-run with the pilot cluster's
coordinates (`--lat/--lon`) once they are confirmed before using the mix for the village.

**Plugging into the village.** `crop_mix_from_s2()` returns `crop_mix_rabi` and `crop_mix_kharif`
with the same keys as constants.yaml. Cropland is kharif-only + rabi-only + double-cropped pixels; a
plot is fallow in a season when it carried no crop then. NDVI cannot split wheat from potato, so the
rabi crop share is divided in the existing 0.65 : 0.20 ratio. `village.py` is unchanged; to use it,
the generator would read `crop_mix_from_s2()["crop_mix_rabi"]` (and kharif) instead of
`C.get("crop_mix_rabi")`. There is no zaid mapping. See docs/decisions/0006.
