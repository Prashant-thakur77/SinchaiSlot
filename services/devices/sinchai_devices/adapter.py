"""DriveAdapter: the one interface the edge controller and the platform use to talk to a pump drive.

Implementations
  * AltivarModbusAdapter   - real Altivar Solar ATV320 over Modbus TCP (gateway) or RTU (RS-485)
  * InProcessAltivar       - the AltivarModel in the same process (tests, Prayogshala, offline demo)

Both read and write only registers marked verified in docs/schneider/register_map.yaml.
"""

from __future__ import annotations

import time
from datetime import UTC, datetime
from typing import Protocol

from pydantic import BaseModel

from . import altivar_map as M
from .altivar_model import AltivarModel


class DriveTelemetry(BaseModel):
    ts: str
    state: str
    eta: int
    hmis: int
    freq_hz: float
    speed_rpm: float
    current_a: float
    power_pct: float
    power_kw: float
    motor_v: float
    thermal_pct: float
    energy_kwh: float
    run_hours: float
    fault: str | None
    fault_lft: int
    fault_name: str | None
    source: str


class DriveAdapter(Protocol):
    def read_telemetry(self) -> DriveTelemetry: ...
    def start(self, freq_ref_hz: float = 50.0) -> None: ...
    def stop(self) -> None: ...
    def set_reference(self, freq_hz: float) -> None: ...
    def reset_fault(self) -> None: ...
    def close(self) -> None: ...


def _decode(regs: dict[int, int], rated_kw: float, source: str) -> DriveTelemetry:
    A = M.addr
    eta = regs.get(A("ETA"), 0)
    unt = regs.get(A("UNT"), 1)
    aph_scale = {0: 0.001, 1: 1.0, 2: 1000.0}.get(unt & 0b11, 1.0)
    rth_scale = {0: 1 / 3600, 1: 1 / 60, 2: 1.0}.get((unt >> 4) & 0b11, 1.0)
    lft = regs.get(A("LFT"), 0)
    f = M.fault_by_lft(lft)
    opr = regs.get(A("OPR"), 0)
    opr = opr - 0x10000 if opr & 0x8000 else opr
    return DriveTelemetry(
        ts=datetime.now(UTC).isoformat(timespec="seconds"),
        state=M.decode_state(eta), eta=eta, hmis=regs.get(A("HMIS"), 0),
        freq_hz=regs.get(A("RFR"), 0) / 10.0, speed_rpm=float(regs.get(A("RFRD"), 0)),
        current_a=regs.get(A("LCR"), 0) / 10.0, power_pct=float(opr), power_kw=round(opr / 100 * rated_kw, 3),
        motor_v=float(regs.get(A("UOP"), 0)), thermal_pct=float(regs.get(A("THD"), 0)),
        energy_kwh=regs.get(A("APH"), 0) * aph_scale, run_hours=regs.get(A("RTH"), 0) * rth_scale,
        fault=f.mnemonic if f else None, fault_lft=lft, fault_name=f.name if f else None, source=source,
    )


class InProcessAltivar:
    """Adapter over an in-process AltivarModel; same register semantics as the Modbus path."""

    def __init__(self, model: AltivarModel | None = None, rated_kw: float | None = None):
        self.model = model or AltivarModel()
        self.rated_kw = rated_kw or self.model.pump.rated_kw

    def _regs(self) -> dict[int, int]:
        self.model.tick()
        return dict(self.model.regs)

    def read_telemetry(self) -> DriveTelemetry:
        return _decode(self._regs(), self.rated_kw, "Schneider Altivar Solar - simulated")

    def _w(self, mn: str, v: int) -> None:
        self.model.write(M.addr(mn), v)

    def start(self, freq_ref_hz: float = 50.0) -> None:
        self._w("CMD", M.CMD_SHUTDOWN)
        self._w("LFR", int(round(freq_ref_hz * 10)))
        self._w("CMD", M.CMD_ENABLE_OPERATION)

    def stop(self) -> None:
        self._w("CMD", M.CMD_SWITCH_ON)

    def set_reference(self, freq_hz: float) -> None:
        self._w("LFR", int(round(freq_hz * 10)))

    def reset_fault(self) -> None:
        self._w("CMD", 0)
        self._w("CMD", M.CMD_FAULT_RESET)

    def close(self) -> None:
        pass


class AltivarModbusAdapter:
    """Real drive over Modbus TCP (e.g. through a TCP/RTU gateway) or RTU.

    Prerequisite on the drive (NVE41308 p.32, p.60; PKR47019 p.96): Modbus address ADD set to 1..247
    (factory OFF) and the command/reference channel set to Modbus (or DI4 selecting channel 2).
    """

    def __init__(self, host: str | None = None, port: int = 502, unit: int = 1, rated_kw: float = 3.7,
                 serial_port: str | None = None, baudrate: int = 19200, timeout_s: float = 2.0):
        from pymodbus.client import ModbusSerialClient, ModbusTcpClient

        self.unit = unit
        self.rated_kw = rated_kw
        if serial_port:
            self.client = ModbusSerialClient(port=serial_port, baudrate=baudrate, parity="E", stopbits=1,
                                             bytesize=8, timeout=timeout_s)
            self.source = f"Altivar RTU {serial_port}"
        else:
            self.client = ModbusTcpClient(host or "127.0.0.1", port=port, timeout=timeout_s)
            self.source = f"Altivar TCP {host}:{port}"
        if not self.client.connect():
            raise ConnectionError(f"cannot connect to drive ({self.source})")

    def _read(self, address: int, count: int) -> list[int]:
        rr = self.client.read_holding_registers(address, count=count, device_id=self.unit)
        if rr.isError():
            raise OSError(f"Modbus read {address} x{count} failed: {rr}")
        return list(rr.registers)

    def _write(self, mn: str, value: int) -> None:
        rr = self.client.write_register(M.addr(mn), value & 0xFFFF, device_id=self.unit)
        if rr.isError():
            raise OSError(f"Modbus write {mn} failed: {rr}")

    def read_telemetry(self) -> DriveTelemetry:
        A = M.addr
        regs: dict[int, int] = {}
        base = A("ETA")
        # 3201..3209 are all documented (ETA RFR FRH LCR OTR ETI ULN UOP THD); 3210 is not, so OPR is read alone.
        for i, v in enumerate(self._read(base, 9)):
            regs[base + i] = v
        for mn in ("OPR", "HMIS", "RFRD", "LFT"):
            regs[A(mn)] = self._read(A(mn), 1)[0]
        aph, rth = self._read(A("APH"), 2)  # 3230, 3231
        regs[A("APH")], regs[A("RTH")] = aph, rth
        regs[A("UNT")] = self._read(A("UNT"), 1)[0]  # read after APH (NVE41295 p.66)
        return _decode(regs, self.rated_kw, self.source)

    def _wait_state(self, want: str, timeout_s: float = 3.0) -> None:
        t0 = time.monotonic()
        while time.monotonic() - t0 < timeout_s:
            if M.decode_state(self._read(M.addr("ETA"), 1)[0]) == want:
                return
            time.sleep(0.05)
        raise TimeoutError(f"drive did not reach {want}")

    def start(self, freq_ref_hz: float = 50.0) -> None:
        # Sequence from NVE41308 p.51-52.
        self._write("CMD", M.CMD_SHUTDOWN)
        self._wait_state("ready_to_switch_on")
        self._write("LFR", int(round(freq_ref_hz * 10)))
        self._write("CMD", M.CMD_ENABLE_OPERATION)
        self._wait_state("operation_enabled")

    def stop(self) -> None:
        self._write("CMD", M.CMD_SWITCH_ON)  # disable operation: ramp stop

    def set_reference(self, freq_hz: float) -> None:
        self._write("LFR", int(round(freq_hz * 10)))

    def reset_fault(self) -> None:
        self._write("CMD", 0)
        self._write("CMD", M.CMD_FAULT_RESET)

    def close(self) -> None:
        self.client.close()
