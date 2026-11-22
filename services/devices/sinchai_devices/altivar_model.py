"""Behavioural model of an Altivar Solar ATV320 driving a 5 HP pump, exposed through the verified
register map. Used by the Modbus simulator and by in-process tests.

What is modelled
  * CiA402 state machine driven by CMD (8501); ETA (3201) and HMIS (3240) reflect it
  * frequency reference LFR (8502, 0.1 Hz); output frequency RFR (3202) ramps at ACC/DEC (9001/9002)
  * solar-limited MPPT: the drive runs at the speed the available PV power can sustain, never above
    the reference; below the pump cut-off it idles at 0 Hz (low-light behaviour, PKR47019 p.122)
  * motor power OPR (3211, % of nominal), current LCR (3204), motor voltage UOP (3208), thermal THD,
    energy APH (3230) with unit bits in UNT (3234), run time RTH (3231)
  * dry run: an injected dry-well event drops the hydraulic load; after ULT seconds below LUL the
    drive trips ULF (process underload, PKR47019 p.119-120)
  * fault injection of any documented fault; LFT (7121) and DP1..DP8 history

Values that the manuals do not expose over Modbus (PV voltage, PV power, MPPT state, estimated flow)
are NOT given register addresses; the model keeps them as Python attributes for the UI only.
"""

from __future__ import annotations

import math
import time
from collections.abc import Callable
from dataclasses import dataclass, field

from . import altivar_map as M
from .physics import PumpModel, default_pump

V_NOM = 380.0
PF = 0.82
NSP_RPM = 2880  # nominal motor speed of a 2-pole 50 Hz motor


def _u16(v: float) -> int:
    return int(round(v)) & 0xFFFF


@dataclass
class AltivarModel:
    pump: PumpModel = field(default_factory=default_pump)
    pv_kw: Callable[[float], float] = lambda t: 4.0
    clock: Callable[[], float] = time.monotonic
    regs: dict[int, int] = field(default_factory=dict)
    state: str = "switch_on_disabled"
    freq_hz: float = 0.0
    ref_hz: float = 50.0
    energy_wh: float = 0.0
    run_s: float = 0.0
    power_kw: float = 0.0
    flow_m3h: float = 0.0
    thermal_pct: float = 30.0
    dry_run: bool = False
    _underload_s: float = 0.0
    _last: float | None = None
    fault: str | None = None
    history: list[str] = field(default_factory=list)
    low_light: bool = False

    def __post_init__(self) -> None:
        A = M.addr
        defaults = {
            A("ADD"): 1, A("TBR"): 0, A("TTO"): 100,
            A("ACC"): 100, A("DEC"): 100,  # 10.0 s, Altivar Solar factory setting (PKR47019 p.96)
            A("HSP"): 500, A("LSP"): 0, A("TFR"): 600,
            A("UNS"): int(V_NOM), A("FRS"): 500, A("NSP"): NSP_RPM,
            A("NCR"): _u16(self._current(self.pump.rated_kw) * 10),
            A("ULT"): 20, A("LUL"): 60, A("LUN"): 50, A("UDL"): 1, A("FTU"): 10,
            A("LFR"): 500, A("CMD"): 0,
        }
        self.regs.update(defaults)
        self._publish()

    # ---------------- helpers ----------------
    def _current(self, p_kw: float) -> float:
        return p_kw * 1000 / (math.sqrt(3) * V_NOM * PF) if p_kw > 0 else 0.0

    def _accel_hz_per_s(self) -> float:
        return 50.0 / max(self.regs.get(M.addr("ACC"), 100) / 10.0, 0.1)

    def _decel_hz_per_s(self) -> float:
        return 50.0 / max(self.regs.get(M.addr("DEC"), 100) / 10.0, 0.1)

    # ---------------- external events ----------------
    def inject_fault(self, mnemonic: str) -> None:
        if mnemonic not in M.faults():
            raise KeyError(f"unknown fault {mnemonic}")
        self.fault = mnemonic
        self.state = "fault"
        self.history.insert(0, mnemonic)
        self.history = self.history[:8]
        self.freq_hz = 0.0
        self._publish()

    def set_dry_run(self, on: bool) -> None:
        self.dry_run = on

    # ---------------- Modbus writes ----------------
    def write(self, address: int, value: int) -> None:
        self.regs[address] = value & 0xFFFF
        if address == M.addr("CMD"):
            self._on_cmd(value & 0xFFFF)
        elif address == M.addr("LFR"):
            v = value - 0x10000 if value & 0x8000 else value
            self.ref_hz = max(0.0, min(v / 10.0, self.regs.get(M.addr("HSP"), 500) / 10.0))
        elif address == M.addr("LFRD"):
            v = value - 0x10000 if value & 0x8000 else value
            self.ref_hz = max(0.0, min(v / NSP_RPM * 50.0, 50.0))
        self._publish()

    def _on_cmd(self, cmd: int) -> None:
        if self.state == "fault":
            if cmd & M.CMD_FAULT_RESET:
                # Faults clear only once the cause is gone; dry run must have recovered.
                if self.fault == "ULF" and self.dry_run:
                    return
                self.fault = None
                self.state = "switch_on_disabled"
            return
        # CiA402 command decoding on bits 0-3 (NVE41308 p.46, p.51-52).
        b0, b1, b2, b3 = (cmd >> 0) & 1, (cmd >> 1) & 1, (cmd >> 2) & 1, (cmd >> 3) & 1
        if not b1:  # Disable voltage
            self.state = "switch_on_disabled"
        elif not b2:  # Quick stop
            self.state = "quick_stop_active" if self.state == "operation_enabled" else "switch_on_disabled"
        elif not b0:  # Shutdown (x110)
            self.state = "ready_to_switch_on"
        elif not b3:  # Switch on / disable operation (0111)
            if self.state in ("ready_to_switch_on", "switched_on", "operation_enabled"):
                self.state = "switched_on"
        else:  # Enable operation (1111); allowed from state 3 directly (NVE41308 p.52)
            if self.state in ("ready_to_switch_on", "switched_on", "operation_enabled"):
                self.state = "operation_enabled"

    # ---------------- physics ----------------
    def tick(self, now: float | None = None) -> None:
        now = self.clock() if now is None else now
        dt = 0.0 if self._last is None else max(0.0, min(now - self._last, 5.0))
        self._last = now
        pv = max(float(self.pv_kw(now)), 0.0)
        target = 0.0
        self.low_light = False
        if self.state == "operation_enabled":
            n_avail = float(self.pump.speed_for_power(min(pv, self.pump.rated_kw)))
            f_avail = n_avail * self.pump.f_nom_hz
            if n_avail <= self.pump.n_cutoff + 0.01:
                self.low_light = True
                f_avail = 0.0
            target = min(self.ref_hz, f_avail)
        if self.freq_hz < target:
            self.freq_hz = min(target, self.freq_hz + self._accel_hz_per_s() * dt)
        else:
            self.freq_hz = max(target, self.freq_hz - self._decel_hz_per_s() * dt)
        n = self.freq_hz / self.pump.f_nom_hz
        p = float(self.pump.power_at_speed(n)) if n > 0 else 0.0
        q = float(self.pump.flow_at_speed(n)) if n > 0 else 0.0
        if self.dry_run and n > 0:
            p *= 0.35  # no water: the impeller churns air, load collapses
            q = 0.0
        self.power_kw = min(p, pv) if self.state == "operation_enabled" else 0.0
        self.flow_m3h = q if self.state == "operation_enabled" else 0.0
        self.energy_wh += self.power_kw * 1000 * dt / 3600
        if self.freq_hz > 0:
            self.run_s += dt
        load = self.power_kw / self.pump.rated_kw
        self.thermal_pct += (30 + 70 * load - self.thermal_pct) * min(dt / 600, 1)
        # Process underload (dry run): ULF after ULT seconds below LUL % of expected load.
        if self.state == "operation_enabled" and n > self.pump.n_cutoff + 0.02:
            expected = float(self.pump.power_at_speed(n))
            lul = self.regs.get(M.addr("LUL"), 60) / 100
            if self.regs.get(M.addr("UDL"), 1) and self.power_kw < lul * expected:
                self._underload_s += dt
            else:
                self._underload_s = 0.0
            if self._underload_s >= self.regs.get(M.addr("ULT"), 20):
                self._underload_s = 0.0
                self.inject_fault("ULF")
                return
        self._publish()

    # ---------------- register image ----------------
    def _eta(self) -> int:
        base = {
            "switch_on_disabled": 0x0050,
            "ready_to_switch_on": 0x0031,
            "switched_on": 0x0033,
            "operation_enabled": 0x0037,
            "quick_stop_active": 0x0017,
            "fault": 0x0018,
        }[self.state]
        eta = base | M.ETA_REMOTE_BIT
        if self.state == "operation_enabled" and abs(self.freq_hz - min(self.ref_hz, 50)) < 0.05:
            eta |= M.ETA_TARGET_REACHED_BIT
        return eta

    def _hmis(self) -> int:
        if self.state == "fault":
            return M.HMIS["FLT"]
        if self.state != "operation_enabled":
            return M.HMIS["RDY"] if self.state in ("ready_to_switch_on", "switched_on") else M.HMIS["NST"]
        target = min(self.ref_hz, 50)
        if self.freq_hz < target - 0.05 and not self.low_light:
            return M.HMIS["ACC"]
        return M.HMIS["RUN"]

    def _publish(self) -> None:
        A = M.addr
        f = self.fault
        lft = M.faults()[f].lft_value if f and M.faults()[f].lft_value is not None else 0
        img = {
            A("ETA"): self._eta(),
            A("HMIS"): self._hmis(),
            A("RFR"): _u16(self.freq_hz * 10),
            A("RFRD"): _u16(self.freq_hz / 50 * NSP_RPM),
            A("LCR"): _u16(self._current(self.power_kw) * 10),
            A("OPR"): _u16(self.power_kw / self.pump.rated_kw * 100),
            A("UOP"): _u16(V_NOM * min(self.freq_hz / 50, 1.0)),
            A("ULN"): _u16(4200),  # mains-equivalent of the DC bus; simulated constant
            A("THD"): _u16(self.thermal_pct),
            A("THR"): _u16(self.thermal_pct),
            A("APH"): _u16(self.energy_wh / 1000),  # kWh with UNT bits 0-1 = 1
            A("UNT"): 0b01 | (0b10 << 4) | (0b10 << 2),  # APH kWh, PTH h, RTH h
            A("RTH"): _u16(self.run_s / 3600),
            A("LFT"): lft,
        }
        for i, mn in enumerate(self.history[:8]):
            v = M.faults()[mn].lft_value
            img[A(f"DP{i + 1}")] = v if v is not None else 0
        self.regs.update(img)

    def read(self, address: int, count: int = 1) -> list[int]:
        return [self.regs.get(address + i, 0) for i in range(count)]

    # ---------------- UI-only quantities (no Modbus register exists) ----------------
    def ui_extras(self, now: float | None = None) -> dict:
        now = self.clock() if now is None else now
        return {"pv_kw_available": round(float(self.pv_kw(now)), 3), "flow_m3h_true": round(self.flow_m3h, 2),
                "low_light": self.low_light, "dry_run_injected": self.dry_run,
                "note": "PV power, PV voltage and MPPT state have no documented Modbus register (UNVERIFIED)."}
