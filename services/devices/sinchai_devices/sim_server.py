"""SimulatedAltivar: a Modbus TCP server that behaves like an Altivar Solar ATV320 on a 5 HP pump.

Run:  uv run python -m sinchai_devices.sim_server --port 5020 --profile clear --speed 60

Profiles drive the available PV power: `clear` (bell curve), `demo` (the real held-out demo day from
reports/proof.json, compressed by --speed), or `constant`. A small HTTP control endpoint is not
needed: faults and dry-run are injected through the platform API, which holds the model in-process,
or by writing to the simulator-only control register block described below.

Simulator-only control registers (NOT Altivar registers; outside the documented map, 60000+):
  60000 inject fault: write the LFT numeric value of a documented fault
  60001 dry run: 1 = well dry, 0 = water back
"""

from __future__ import annotations

import argparse
import asyncio
import json
import math
import time
from pathlib import Path

from pymodbus.server import StartAsyncTcpServer
from pymodbus.simulator import DataType, SimData, SimDevice

from . import altivar_map as M
from .altivar_model import AltivarModel

SIM_CTRL_FAULT = 60000
SIM_CTRL_DRY = 60001


def pv_profile(kind: str, speed: float, peak_kw: float = 4.2):
    t0 = time.monotonic()
    if kind == "constant":
        return lambda now: peak_kw
    if kind == "demo":
        proof = Path(__file__).resolve().parents[3] / "reports" / "proof.json"
        day = json.loads(proof.read_text())["demo_day"]
        series = day["pv_actual_kw"]

        def f(now: float) -> float:
            h = ((now - t0) * speed / 3600) % len(series)
            i = int(h)
            j = min(i + 1, len(series) - 1)
            return series[i] + (series[j] - series[i]) * (h - i)
        return f

    def bell(now: float) -> float:
        h = 6 + ((now - t0) * speed / 3600) % 12
        return max(0.0, math.sin(math.pi * (h - 6) / 12)) * peak_kw
    return bell


def build_device(model: AltivarModel, device_id: int = 1) -> SimDevice:
    addrs = sorted({a for a in model.regs} | {r.address for r in M.registers().values()
                                               if r.verified and r.address is not None})
    blocks = [SimData(address=a, values=[model.regs.get(a, 0)], datatype=DataType.REGISTERS) for a in addrs]
    blocks.append(SimData(address=SIM_CTRL_FAULT, values=[0, 0], datatype=DataType.REGISTERS))

    async def action(fc, start_address, address, count, registers, set_values):
        if set_values:
            for i, v in enumerate(set_values):
                a = address + i
                if a == SIM_CTRL_FAULT and v:
                    f = M.fault_by_lft(int(v))
                    if f:
                        model.inject_fault(f.mnemonic)
                elif a == SIM_CTRL_DRY:
                    model.set_dry_run(bool(v))
                else:
                    model.write(a, int(v))
        model.tick()
        for a, v in model.regs.items():
            off = a - start_address
            if 0 <= off < len(registers):
                registers[off] = v
        return None

    return SimDevice(id=device_id, simdata=blocks, action=action)


async def serve(port: int, profile: str, speed: float) -> None:
    clock_t0 = time.monotonic()
    model = AltivarModel(pv_kw=pv_profile(profile, speed), clock=lambda: clock_t0 + (time.monotonic() - clock_t0) * speed)
    model.regs[M.addr("ADD")] = 1
    device = build_device(model)

    async def ticker():
        while True:
            model.tick()
            await asyncio.sleep(0.5)

    asyncio.get_running_loop().create_task(ticker())
    print(f"SimulatedAltivar listening on 0.0.0.0:{port} (profile={profile}, speed x{speed})", flush=True)
    await StartAsyncTcpServer(context=device, address=("0.0.0.0", port))


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=5020)
    ap.add_argument("--profile", default="clear", choices=["clear", "demo", "constant"])
    ap.add_argument("--speed", type=float, default=1.0)
    a = ap.parse_args()
    asyncio.run(serve(a.port, a.profile, a.speed))


if __name__ == "__main__":
    main()
