"""Rasid ledger stored in the database, using the hash chain from sinchai_rasid."""

from __future__ import annotations

from dataclasses import asdict
from datetime import datetime, timedelta

from sinchai_rasid.ledger import GENESIS, Receipt, make_water_receipt
from sinchai_schemas import constants as C

from . import db


def _head(s) -> tuple[str, int]:
    last = s.query(db.LedgerRow).order_by(db.LedgerRow.seq.desc()).first()
    return (last.hash, last.seq) if last else (GENESIS, 0)


def _row(r: Receipt) -> db.LedgerRow:
    return db.LedgerRow(
        receipt_id=r.receipt_id, kind=r.kind, booking_id=r.booking_id, pump_id=r.pump_id, plot_id=r.plot_id,
        farmer_ref=r.farmer_ref, tenant=r.tenant, start=r.start, end=r.end, kwh=r.kwh, m3=r.m3,
        amount_rs=r.amount_rs, diesel_l_avoided=r.diesel_l_avoided, co2_kg_avoided=r.co2_kg_avoided,
        payload=asdict(r), hash=r.hash, prev_hash=r.prev_hash,
    )


def append(s, r: Receipt) -> db.LedgerRow:
    prev, _ = _head(s)
    r.prev_hash = prev
    r.hash = r.compute_hash()
    row = _row(r)
    s.add(row)
    s.commit()
    return row


def append_many(s, rs: list[Receipt]) -> int:
    """Chain and store many receipts in order with one commit (seeding history)."""
    prev, _ = _head(s)
    rows = []
    for r in rs:
        r.prev_hash = prev
        r.hash = r.compute_hash()
        prev = r.hash
        rows.append(_row(r))
    s.add_all(rows)
    s.commit()
    return len(rows)


def record_water_receipt(s, b: db.Booking, m3: float, kwh: float, now: datetime) -> dict:
    f = s.get(db.Farmer, b.farmer_id)
    n = s.query(db.LedgerRow).count() + 1
    start = (now - timedelta(minutes=max(m3 / 30 * 60, 1))).isoformat(timespec="minutes")
    r = make_water_receipt(f"R{n:06d}", b.id, b.pump_id, b.plot_id, b.farmer_id, bool(f and f.tenant), start,
                           now.isoformat(timespec="minutes"), kwh, m3, C.get("sinchaislot_tariff_rs_per_m3"))
    row = append(s, r)
    return row_to_dict(row)


def row_to_dict(r: db.LedgerRow) -> dict:
    return {"seq": r.seq, "receipt_id": r.receipt_id, "kind": r.kind, "booking_id": r.booking_id,
            "pump_id": r.pump_id, "plot_id": r.plot_id, "farmer_ref": r.farmer_ref, "tenant": r.tenant,
            "start": r.start, "end": r.end, "kwh": r.kwh, "m3": r.m3, "amount_rs": r.amount_rs,
            "diesel_l_avoided": r.diesel_l_avoided, "co2_kg_avoided": r.co2_kg_avoided,
            "method": r.payload.get("method"), "hash": r.hash, "prev_hash": r.prev_hash}


def receipts(s, limit: int | None = None) -> list[Receipt]:
    q = s.query(db.LedgerRow).order_by(db.LedgerRow.seq)
    rows = q.all() if limit is None else q.limit(limit).all()
    return [Receipt(**r.payload) for r in rows]


def verify(s) -> dict:
    prev = GENESIS
    rows = s.query(db.LedgerRow).order_by(db.LedgerRow.seq).all()
    for r in rows:
        rec = Receipt(**r.payload)
        if r.prev_hash != prev or rec.compute_hash() != r.hash or rec.m3 != r.m3 or rec.kwh != r.kwh:
            return {"ok": False, "first_bad_seq": r.seq, "checked": len(rows)}
        prev = r.hash
    return {"ok": True, "first_bad_seq": None, "checked": len(rows), "head": prev}
