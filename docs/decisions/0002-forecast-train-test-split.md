# 0002 Forecast training and held-out years

**Decision.** Truth is NASA POWER hourly GHI (2016-2025). Numerical weather prediction features come
from the Open-Meteo historical forecast API (GFS from 2022, ICON from late 2022, ECMWF IFS 0.25 deg
from 2024; missing values are left as NaN and handled by the tree models). Models are trained on
2022-2023 and evaluated on **held-out 2024-2025**. The climatology baseline uses 2016-2023 NASA
history only. The persistence baseline uses the previous day's observed irradiance.

**Why.** The plan asks for held-out later years. Archived multi-model forecasts only exist from 2022,
so the earlier NASA years are used for climatology and for the 365-day village simulation weather,
not for training the NWP-based model.

**Caveat (published with the results).** The historical forecast API stitches the first hours of
successive model runs, so its lead time is shorter than a true 24-48 h day-ahead forecast. The
forecast-error stress test in Prayogshala covers the extra error of a real day-ahead forecast.
