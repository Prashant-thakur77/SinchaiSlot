"""Altivar Solar ATV320 register map and fault table, loaded from docs/schneider/.

The YAML files there were built from Schneider's official manuals (NVE41308, NVE41295, NVE41316,
PKR47019) with a page reference per entry. This module refuses to use an address that is not
marked verified, so no device value is ever invented in code.
"""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

import yaml

DOCS = Path(__file__).resolve().parents[3] / "docs" / "schneider"


@dataclass(frozen=True)
class Register:
    mnemonic: str
    address: int | None
    access: str | None
    scale: float | None
    unit: str | None
    verified: bool
    description: str


@dataclass(frozen=True)
class Fault:
    mnemonic: str
    name: str
    lft_value: int | None
    description: str
    causes: tuple[str, ...]
    remedies: tuple[str, ...]
    clearing: str
    verified: bool


@lru_cache(maxsize=1)
def registers() -> dict[str, Register]:
    raw = yaml.safe_load((DOCS / "register_map.yaml").read_text())
    out = {}
    for r in raw["registers"]:
        sc = r.get("scale")
        out[r["mnemonic"]] = Register(
            mnemonic=r["mnemonic"], address=r.get("address"), access=r.get("access"),
            scale=float(sc) if isinstance(sc, (int, float)) else None, unit=r.get("unit"),
            verified=bool(r.get("verified")), description=str(r.get("description", "")),
        )
    return out


@lru_cache(maxsize=1)
def faults() -> dict[str, Fault]:
    raw = yaml.safe_load((DOCS / "fault_codes.yaml").read_text())
    out = {}
    for f in raw["faults"]:
        out[f["mnemonic"]] = Fault(
            mnemonic=f["mnemonic"], name=f.get("name", ""), lft_value=f.get("lft_value"),
            description=f.get("description", ""), causes=tuple(f.get("causes", [])),
            remedies=tuple(f.get("remedies", [])), clearing=f.get("clearing", ""), verified=bool(f.get("verified")),
        )
    return out


def fault_by_lft(value: int) -> Fault | None:
    if value == 0:
        return None
    return next((f for f in faults().values() if f.lft_value == value), None)


def addr(mnemonic: str) -> int:
    r = registers()[mnemonic]
    if not r.verified or r.address is None:
        raise KeyError(f"{mnemonic} is UNVERIFIED in docs/schneider/register_map.yaml; no address is used")
    return r.address


def unverified() -> list[str]:
    return [m for m, r in registers().items() if not r.verified]


# CiA402 / Drivecom command words (NVE41308 p.46)
CMD_SHUTDOWN = 0x0006
CMD_SWITCH_ON = 0x0007
CMD_ENABLE_OPERATION = 0x000F
CMD_DISABLE_VOLTAGE = 0x0000
CMD_QUICK_STOP = 0x0002
CMD_FAULT_RESET = 0x0080

# ETA & 0x006F state decoding (NVE41308 p.49)
STATE_SWITCH_ON_DISABLED = 0x0040
STATE_READY = 0x0021
STATE_SWITCHED_ON = 0x0023
STATE_OPERATION_ENABLED = 0x0027
STATE_QUICK_STOP = 0x0007
ETA_FAULT_BIT = 0x0008
ETA_VOLTAGE_BIT = 0x0010
ETA_REMOTE_BIT = 0x0200
ETA_TARGET_REACHED_BIT = 0x0400

# HMIS drive state enumeration (NVE41316): only values documented there are used.
HMIS = {"RDY": 2, "NST": 3, "RUN": 4, "ACC": 5, "DEC": 6, "FLT": 23}


def decode_state(eta: int) -> str:
    if eta & ETA_FAULT_BIT:
        return "fault"
    m = eta & 0x006F
    return {
        STATE_SWITCH_ON_DISABLED: "switch_on_disabled",
        STATE_READY: "ready_to_switch_on",
        STATE_SWITCHED_ON: "switched_on",
        STATE_OPERATION_ENABLED: "operation_enabled",
        STATE_QUICK_STOP: "quick_stop_active",
    }.get(m, f"unknown_0x{m:04x}")
