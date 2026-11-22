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
