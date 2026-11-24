"""Pump Doctor: find slow pump problems from readings the Altivar drive already reports.

Two ratios, from output frequency (RFR) and motor power (OPR) only:
  sun  = power drawn / power the neighbouring pumps draw in the same sun-limited hours
  load = power drawn / power a healthy pump draws at the same frequency

  sun falls, load steady   -> panels: dust, shade or a failed module
  load rises               -> friction: worn bearing or clogged impeller
  load falls               -> water: the water table is dropping and the pump lifts higher for less

Each is compared with the same pump one to two months earlier, so slow seasonal movement of the water
table and fixed differences between pumps cancel. Two things cannot be seen this way: dust that falls
on every pump of the cluster at once, and a leak inside the pump that leaves power unchanged.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from .physics import RHO_G, PumpModel, default_pump

ADVICE = {
    "panels": {"en": "Panels are giving less than the sun allows. Wash them and look for shade or a broken module.",
               "hi": "पैनल धूप से कम बिजली दे रहे हैं। पैनल धोएँ और छाया या टूटा पैनल देखें।"},
    "friction": {"en": "The motor is working harder than it should. Check the bearing and clear the impeller.",
                 "hi": "मोटर ज़रूरत से ज़्यादा ज़ोर लगा रही है। बेयरिंग और इम्पेलर जाँचें।"},
    "water": {"en": "The water is getting deeper. Measure the well and lower the season's water budget if confirmed.",
              "hi": "पानी नीचे जा रहा है। कुएँ का स्तर नापें और सही हो तो सीज़न का पानी बजट घटाएँ।"},
    "ok": {"en": "Running as it did when it was new.", "hi": "पंप ठीक चल रहा है।"},
}


@dataclass(frozen=True)
class PumpCondition:
    """A pump with extra static head (m) and a friction multiplier on power."""

    extra_head_m: float = 0.0
    friction: float = 1.0
    pump: PumpModel = field(default_factory=default_pump)

    def power_at(self, n: np.ndarray) -> np.ndarray:
        p = self.pump
        n = np.asarray(n, dtype=float)
        hs = p.hs + self.extra_head_m
        q = np.sqrt(np.clip((p.h0 * n**2 - hs) / (p.a + p.b), 0, None))
        hyd = RHO_G * (q / 3600) * (hs + p.b * q**2) / 1000 / p.eta_w2w
        raw = RHO_G * (p.q_rated_m3h / 3600) * p.h_rated_m / 1000 / p.eta_w2w
        return np.maximum(hyd, 0.35 * raw * n**3) * p.rated_kw / raw * self.friction

    def speed_for(self, kw: np.ndarray) -> np.ndarray:
        n = np.linspace(0, 1, 1001)
        curve = np.maximum.accumulate(self.power_at(n))
        return np.interp(np.asarray(kw, dtype=float), curve, n)

    @property
    def cutoff_n(self) -> float:
        return float(np.sqrt((self.pump.hs + self.extra_head_m) / self.pump.h0))


@dataclass
class Thresholds:
    panels: float = 0.12
    friction: float = 0.06
    water: float = 0.06


@dataclass
class PumpDoctor:
    thresholds: Thresholds = field(default_factory=Thresholds)
    window_d: int = 10
    gap_d: int = 30  # the comparison window ends this long before today
    reference_d: int = 30
    min_hours: int = 2

    @property
    def baseline_d(self) -> int:
        return self.window_d + self.gap_d + self.reference_d

    def daily_ratios(self, hours: pd.DataFrame) -> pd.DataFrame:
        """`hours`: index time, columns freq_hz, power_kw, peer_kw (NaN when no neighbour ran)."""
        pump = default_pump()
        day = hours.index.floor("D")
        sunny = (hours["power_kw"] > 0.8) & (hours["freq_hz"] < 49.5) & hours["peer_kw"].notna()
        g = hours[sunny].groupby(day[sunny])[["power_kw", "peer_kw"]].sum()
        g = g[hours[sunny].groupby(day[sunny]).size() >= self.min_hours]
        mid = (hours["freq_hz"] > 41) & (hours["freq_hz"] < 49.9)
        h = hours[mid]
        healthy = PumpCondition().power_at(h["freq_hz"].to_numpy() / pump.f_nom_hz)
        w = pd.DataFrame({"p": h["power_kw"].to_numpy(), "h": healthy}, index=day[mid]).groupby(level=0).sum()
        return pd.DataFrame({"sun": np.log(g["power_kw"] / g["peer_kw"]), "load": np.log(w["p"] / w["h"])}).asfreq("D")

    def scores(self, daily: pd.DataFrame) -> pd.DataFrame:
        now = daily.rolling(self.window_d, min_periods=4).median()
        ref = daily.rolling(self.reference_d, min_periods=8).median().shift(self.window_d + self.gap_d)
        d = now - ref
        return pd.DataFrame({"panels": -d["sun"], "friction": d["load"], "water": -d["load"]})

    def first_alert(self, scores: pd.DataFrame, after: pd.Timestamp | None = None) -> tuple[pd.Timestamp, str] | None:
        s = scores if after is None else scores[scores.index >= after]
        rel = pd.DataFrame({k: s[k] / getattr(self.thresholds, k) for k in ("panels", "friction", "water")})
        hit = rel.max(axis=1) >= 1
        if not hit.any():
            return None
        day = hit.idxmax()
        row = rel.loc[day]
        # The hydraulic signature is independent of the sun, so it wins when both have crossed.
        cls = "friction" if row["friction"] >= 1 else "water" if row["water"] >= 1 else "panels"
        return day, cls
