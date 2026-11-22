"""Rasid: verified receipts and an append-only, hash-chained ledger.

Every completed booking produces one receipt. Each receipt carries the SHA-256 of the previous
receipt, so editing or deleting any past receipt breaks every hash after it; `verify()` detects it.
A Merkle root over a period's receipt hashes goes into each funder report and claim pack, so a
funder can check a single receipt against the report without the whole ledger.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, field
from pathlib import Path

from sinchai_schemas import constants as C

GENESIS = "0" * 64


def diesel_avoided_l(m3: float) -> float:
    """Diesel a 5 HP diesel pump would burn to deliver the same water (constants, ACIAR)."""
    return m3 / C.get("diesel_pump_flow_m3h") * C.get("diesel_l_per_hour_5hp")


def co2_avoided_kg(diesel_l: float) -> float:
    return diesel_l * C.get("co2_kg_per_l_diesel")


@dataclass
class Receipt:
    receipt_id: str
    kind: str  # "water" | "mill" | "chaff" | "battery"
    booking_id: str | None
    pump_id: str
    plot_id: str | None
    farmer_ref: str | None  # pseudonymous id, never a name or phone number
    tenant: bool | None
    start: str
    end: str
    kwh: float
    m3: float  # drive-estimated
    m3_meter: float | None = None  # optional flow meter reading
    quantity: float | None = None  # kg milled, hours cut, packs charged
    tariff_rs: float = 0.0
    amount_rs: float = 0.0
    diesel_l_avoided: float = 0.0
    co2_kg_avoided: float = 0.0
    method: str = "drive-estimate"  # how m3 was obtained
    prev_hash: str = GENESIS
    hash: str = ""

    def payload(self) -> dict:
        d = asdict(self)
        d.pop("hash")
        return d

    def compute_hash(self) -> str:
        blob = json.dumps(self.payload(), sort_keys=True, separators=(",", ":"), default=str)
        return hashlib.sha256(blob.encode()).hexdigest()


def make_water_receipt(receipt_id: str, booking_id: str, pump_id: str, plot_id: str, farmer_ref: str,
                       tenant: bool, start: str, end: str, kwh: float, m3: float, tariff_rs_per_m3: float,
                       m3_meter: float | None = None) -> Receipt:
    dl = diesel_avoided_l(m3)
    return Receipt(
        receipt_id=receipt_id, kind="water", booking_id=booking_id, pump_id=pump_id, plot_id=plot_id,
        farmer_ref=farmer_ref, tenant=tenant, start=start, end=end, kwh=round(kwh, 4), m3=round(m3, 3),
        m3_meter=m3_meter, tariff_rs=tariff_rs_per_m3, amount_rs=round(m3 * tariff_rs_per_m3, 2),
        diesel_l_avoided=round(dl, 4), co2_kg_avoided=round(co2_avoided_kg(dl), 4),
        method="flow-meter" if m3_meter is not None else "drive-estimate",
    )


@dataclass
class Ledger:
    path: Path | None = None
    receipts: list[Receipt] = field(default_factory=list)

    @property
    def head(self) -> str:
        return self.receipts[-1].hash if self.receipts else GENESIS

    def append(self, r: Receipt) -> Receipt:
        r.prev_hash = self.head
        r.hash = r.compute_hash()
        self.receipts.append(r)
        if self.path:
            with self.path.open("a") as f:
                f.write(json.dumps(asdict(r), default=str) + "\n")
        return r

    def verify(self) -> tuple[bool, int | None]:
        """Return (ok, index of the first bad receipt)."""
        prev = GENESIS
        for i, r in enumerate(self.receipts):
            if r.prev_hash != prev or r.compute_hash() != r.hash:
                return False, i
            prev = r.hash
        return True, None

    @classmethod
    def load(cls, path: Path) -> Ledger:
        led = cls(path=None)
        if path.exists():
            for line in path.read_text().splitlines():
                if line.strip():
                    led.receipts.append(Receipt(**json.loads(line)))
        led.path = path
        return led


def merkle_root(hashes: list[str]) -> str:
    if not hashes:
        return GENESIS
    level = [bytes.fromhex(h) for h in hashes]
    while len(level) > 1:
        if len(level) % 2:
            level.append(level[-1])
        level = [hashlib.sha256(level[i] + level[i + 1]).digest() for i in range(0, len(level), 2)]
    return level[0].hex()


def merkle_proof(hashes: list[str], index: int) -> list[tuple[str, str]]:
    """Sibling path for leaf `index`: list of (side, hash)."""
    level = [bytes.fromhex(h) for h in hashes]
    proof = []
    i = index
    while len(level) > 1:
        if len(level) % 2:
            level.append(level[-1])
        sib = i ^ 1
        proof.append(("L" if sib < i else "R", level[sib].hex()))
        level = [hashlib.sha256(level[j] + level[j + 1]).digest() for j in range(0, len(level), 2)]
        i //= 2
    return proof


def verify_proof(leaf: str, proof: list[tuple[str, str]], root: str) -> bool:
    h = bytes.fromhex(leaf)
    for side, sib in proof:
        s = bytes.fromhex(sib)
        h = hashlib.sha256(s + h if side == "L" else h + s).digest()
    return h.hex() == root
