import asyncio
import socket
import threading
import time

import pytest

from sinchai_devices import altivar_map as M
from sinchai_devices.adapter import AltivarModbusAdapter, InProcessAltivar
from sinchai_devices.altivar_model import AltivarModel
from sinchai_devices.meter import DriveMeter


class FakeClock:
    def __init__(self):
        self.t = 0.0

    def __call__(self):
        return self.t


def drive(pv=4.0):
    clk = FakeClock()
    m = AltivarModel(pv_kw=lambda t: pv, clock=clk)
    return InProcessAltivar(m), m, clk


def test_register_map_refuses_unverified():
    assert M.addr("CMD") == 8501 and M.addr("ETA") == 3201 and M.addr("LFT") == 7121
    with pytest.raises(KeyError):
        M.addr("SOLAR_POWER")
    assert "SOLAR_POWER" in M.unverified()


def test_cia402_start_stop_sequence():
    d, m, clk = drive()
    assert d.read_telemetry().state == "switch_on_disabled"
    d.start(50)
    for _ in range(30):
        clk.t += 1
        m.tick()
    t = d.read_telemetry()
    assert t.state == "operation_enabled"
    assert t.freq_hz == pytest.approx(50.0, abs=0.2)
    assert 3.0 < t.power_kw <= 3.8
    d.stop()
    for _ in range(30):
        clk.t += 1
        m.tick()
    assert d.read_telemetry().freq_hz == 0.0


def test_solar_limited_speed_and_low_light():
    d, m, clk = drive(pv=1.5)
    d.start(50)
    for _ in range(30):
        clk.t += 1
        m.tick()
    t = d.read_telemetry()
    assert 0 < t.freq_hz < 50
    assert t.power_kw <= 1.5 + 0.05
    m.pv_kw = lambda now: 0.2
    for _ in range(30):
        clk.t += 1
        m.tick()
    assert d.read_telemetry().freq_hz == 0.0 and m.low_light


def test_dry_run_trips_ulf_and_reset_needs_water():
    d, m, clk = drive()
    d.start(50)
    for _ in range(20):
        clk.t += 1
        m.tick()
    m.set_dry_run(True)
    for _ in range(40):
        clk.t += 1
        m.tick()
    t = d.read_telemetry()
    assert t.state == "fault" and t.fault == "ULF" and t.fault_lft == 100
    d.reset_fault()
    assert d.read_telemetry().state == "fault"  # cause still present
    m.set_dry_run(False)
    d.reset_fault()
    assert d.read_telemetry().state == "switch_on_disabled"


def test_fault_injection_and_history():
    d, m, _ = drive()
    m.inject_fault("OHF")
    t = d.read_telemetry()
    assert t.fault == "OHF" and t.state == "fault"
    assert m.regs[M.addr("DP1")] == M.faults()["OHF"].lft_value


def test_drive_as_meter_and_calibration():
    d, m, clk = drive()
    d.start(50)
    for _ in range(30):
        clk.t += 1
        m.tick()
    meter = DriveMeter()
    est = meter.estimate(d.read_telemetry())
    assert est.consistent and est.flow_m3h == pytest.approx(30.0, rel=0.05)
    for e, true in [(30, 27.9), (25, 23.4), (28, 26.0)]:
        meter.add_calibration(e, true)
    assert 0.9 < meter.k < 0.96 and meter.k_rse is not None


def _free_port():
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    p = s.getsockname()[1]
    s.close()
    return p


def test_modbus_tcp_end_to_end():
    from pymodbus.server import StartAsyncTcpServer

    from sinchai_devices.sim_server import SIM_CTRL_FAULT, build_device

    port = _free_port()
    model = AltivarModel(pv_kw=lambda t: 4.0)
    dev = build_device(model)
    loop = asyncio.new_event_loop()

    def run():
        asyncio.set_event_loop(loop)
        loop.run_until_complete(StartAsyncTcpServer(context=dev, address=("127.0.0.1", port)))

    th = threading.Thread(target=run, daemon=True)
    th.start()
    for _ in range(50):
        try:
            a = AltivarModbusAdapter("127.0.0.1", port=port)
            break
        except ConnectionError:
            time.sleep(0.1)
    a.start(50)
    time.sleep(0.3)
    t = a.read_telemetry()
    assert t.state == "operation_enabled"
    a.client.write_register(SIM_CTRL_FAULT, M.faults()["OLF"].lft_value, device_id=1)
    t = a.read_telemetry()
    assert t.fault == "OLF"
    a.close()
    loop.call_soon_threadsafe(loop.stop)
