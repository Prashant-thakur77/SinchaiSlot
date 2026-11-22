from datetime import date

import pytest

from sinchai_rasid.audit import audit
from sinchai_rasid.ledger import Ledger, make_water_receipt, merkle_proof, merkle_root, verify_proof
from sinchai_rasid.reports import claim_pack, summarise, to_csv, write_pdf


def _r(i, m3=30.0, kwh=3.7, meter=None, hour=10):
    return make_water_receipt(f"R{i}", f"B{i}", "P1", f"plot{i}", f"F{i % 7}", i % 2 == 0,
                              f"2024-12-{1 + i % 28:02d}T{hour:02d}:00", f"2024-12-{1 + i % 28:02d}T{hour + 1:02d}:00",
                              kwh, m3, 3.0, m3_meter=meter)


def test_diesel_and_co2_from_constants():
    r = _r(0, m3=30.0)
    assert r.diesel_l_avoided == pytest.approx(1.0)
    assert r.co2_kg_avoided == pytest.approx(2.6444)
    assert r.amount_rs == pytest.approx(90.0)


def test_hash_chain_detects_tampering(tmp_path):
    led = Ledger(path=tmp_path / "l.jsonl")
    for i in range(10):
        led.append(_r(i))
    assert led.verify() == (True, None)
    reloaded = Ledger.load(tmp_path / "l.jsonl")
    assert reloaded.verify() == (True, None)
    reloaded.receipts[4].m3 = 999
    ok, idx = reloaded.verify()
    assert not ok and idx == 4


def test_merkle_proof_roundtrip():
    hs = [_r(i).compute_hash() for i in range(7)]
    root = merkle_root(hs)
    for i in range(7):
        assert verify_proof(hs[i], merkle_proof(hs, i), root)
    assert not verify_proof(hs[0], merkle_proof(hs, 1), root)


def test_audit_rules():
    rs = [_r(i) for i in range(60)]
    rs.append(_r(100, m3=200.0, kwh=1.0))  # impossible water
    rs.append(_r(101, m3=20.0, kwh=0.0))  # water without energy
    rs.append(_r(102, m3=30.0, kwh=3.7, meter=15.0))  # meter disagreement
    f = audit(rs, pump_energy_slots=[("2024-12-05T15:00", 2.0)])
    rules = {(x.rule, x.receipt_id) for x in f}
    assert ("R1", "R100") in rules
    assert ("R3", "R101") in rules
    assert ("R4", "R102") in rules
    assert any(x.rule == "R2" for x in f)


def test_reports(tmp_path):
    led = Ledger()
    for i in range(30):
        led.append(_r(i))
    s = summarise(led.receipts)
    assert s["m3"] == pytest.approx(900.0)
    assert to_csv(led.receipts).count("\n") == 31
    cp = claim_pack(led.receipts, "CSR funder", date(2024, 12, 1), date(2024, 12, 31))
    assert len(cp["receipt_hashes"]) == 30
    assert write_pdf(led.receipts, tmp_path / "r.pdf").stat().st_size > 1000
