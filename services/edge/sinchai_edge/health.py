"""Data-health monitor: notice when a pump stops reporting, or reports but is not pumping when it should.

Remote monitoring decays quietly: only about a third of the pumps that ever logged data on one state portal
were still transmitting (constants: ceew_pumps_transmitting_share). The monitor runs on the platform side and
turns silence into an alert for the Saur Mitra and the operator.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime

from sinchai_schemas import constants as C


@dataclass
class PumpHealth:
    pump_id: str
    status: str  # live | late | silent | stalled | never
    last_seen: str | None
    minutes_since: float | None
    reason_en: str
    reason_hi: str
    alert: bool

    def to_dict(self) -> dict:
        return asdict(self)


def assess(pump_id: str, last_seen: datetime | None, now: datetime, *, daylight: bool = True,
           scheduled_water: bool = False, power_kw: float | None = None, sun_kw: float | None = None) -> PumpHealth:
    """Classify one pump. `stalled`: it reports, a water slot is running, the sun is up, but the drive draws
    nothing: the pump is likely dry, tripped or disconnected even though the data looks alive."""
    late, silent = C.get("telemetry_late_after_min"), C.get("telemetry_silent_after_min")
    if last_seen is None:
        return PumpHealth(pump_id, "never", None, None, "Never reported", "कभी डेटा नहीं भेजा", True)
    mins = max((now - last_seen).total_seconds() / 60, 0.0)
    ls = last_seen.isoformat(timespec="minutes")
    if mins >= silent and daylight:
        return PumpHealth(pump_id, "silent", ls, round(mins), f"No data for {mins / 60:.1f} h in daylight",
                          f"{mins / 60:.1f} घंटे से कोई डेटा नहीं", True)
    if mins >= late:
        return PumpHealth(pump_id, "late", ls, round(mins), f"Last message {mins:.0f} min ago",
                          f"आख़िरी संदेश {mins:.0f} मिनट पहले", False)
    if scheduled_water and (sun_kw or 0) > 1.0 and (power_kw or 0) < 0.1:
        return PumpHealth(pump_id, "stalled", ls, round(mins), "Reporting, sun is up, water slot booked, no power drawn",
                          "धूप है, समय बुक है, पर मोटर नहीं चल रही", True)
    return PumpHealth(pump_id, "live", ls, round(mins), "Reporting normally", "ठीक से डेटा आ रहा है", False)
