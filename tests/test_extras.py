"""Cluster, Pump Passport, data health, harvest-linked repayment, water quality, recharge, soil card, VISTAAR."""

from datetime import date, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sinchai_channels.vistaar import classify
from sinchai_edge.health import assess
from sinchai_jal.quality import card, restriction
from sinchai_jal.recharge import pair, pond_m3_per_year
from sinchai_planner.soil import SoilCard, apply, taw_mm_per_m
from sinchai_rasid.credit import Repayment, harvest_date, limit_rs, offer
from sinchai_rasid.ledger import make_water_receipt
from sinchai_rasid.passport import PumpMeta, passport

# ---------------------------------------------------------------- pure modules

def test_water_quality_follows_fao29_bands():
    assert restriction(0.5) == "none"
    assert restriction(1.5) == "slight_moderate"
    assert restriction(3.5) == "severe"
    c = card("P9", 1.5)
    assert c.tds_mg_l == 960
    assert "wheat" in c.crops_ok and "maize" in c.crops_at_risk  # wheat tolerates 4.0, maize 1.1 dS/m
    with pytest.raises(ValueError):
        card("P9", -1)


def test_recharge_pairing_covers_target():
    out = pair(20_000, 1.0)
    for o in out["options"]:
        assert o["total_m3_per_year"] >= 20_000
        assert o["total_cost_rs"] == o["count"] * o["cost_rs_each"]
    assert pond_m3_per_year() > 0
    assert pair(0)["cheapest"] is None


def test_health_states():
    now = datetime(2024, 3, 2, 12, 0)
    assert assess("P", now - timedelta(minutes=2), now).status == "live"
    assert assess("P", now - timedelta(minutes=20), now).status == "late"
    s = assess("P", now - timedelta(hours=2), now)
    assert s.status == "silent" and s.alert
    assert assess("P", now - timedelta(hours=2), now, daylight=False).status == "late"
    st = assess("P", now, now, scheduled_water=True, power_kw=0.0, sun_kw=3.0)
    assert st.status == "stalled" and st.alert
    assert assess("P", None, now).status == "never"


def test_harvest_credit_rules():
    today = date(2024, 3, 2)
    h = harvest_date("wheat", today)
    assert h > today and h.month in (3, 4)
    o = offer(400, "wheat", today, [])
    assert o.eligible and o.pay_now_rs + o.after_harvest_rs == 400
    assert o.after_harvest_rs <= 200  # at most half deferred
    assert o.fee_rs >= 0 and date.fromisoformat(o.due) > h
    overdue = [Repayment(date(2024, 1, 1), 200, None)]
    assert not offer(400, "wheat", today, overdue).eligible
    clean = [Repayment(date(2023, 5, 1), 200, date(2023, 4, 28)) for _ in range(4)]
    assert limit_rs(clean) == 3 * limit_rs([])


def test_passport_scorecard_is_bounded_and_measured():
    rs = [make_water_receipt(f"R{i}", f"B{i}", "P1", "pl", f"F{i % 5}", i % 2 == 0,
                             f"2024-0{1 + i % 2}-{10 + i:02d}T10:30", f"2024-0{1 + i % 2}-{10 + i:02d}T11:30", 2.5, 20.0, 3.0)
          for i in range(10)]
    pp = passport(PumpMeta("P1", "Test", 4.8, "op"), rs, date(2024, 3, 1), uptime=0.98, faults=[{"code": "OHF"}],
                  repayment_on_time=0.9, ledger_verified=True)
    assert 0 <= pp["score"]["value"] <= 100
    assert pp["water_m3"] == 200 and pp["farmers_served"] == 5 and pp["tenant_water_share"] == 0.5
    assert pp["faults"] == [{"code": "OHF", "count": 1}]
    assert sum(pp["score"]["weights"].values()) == 100


def test_soil_card_sets_taw_from_texture():
    assert taw_mm_per_m("sandy loam")[0] == 130
    assert taw_mm_per_m(None)[1].startswith("default")
    r = apply(SoilCard(texture="sandy loam", ph=8.7, ec_dsm=1.2, oc_pct=0.4, n_kg_ha=600), "wheat")
    assert r["irrigate_when_depleted_mm"] < r["default_irrigate_when_depleted_mm"]
    assert r["ratings"]["oc_pct"] == "low" and r["ratings"]["n_kg_ha"] == "high"
    assert len(r["flags"]) == 2


def test_vistaar_topic_classifier():
    assert classify("गेहूँ में रोग लगा है") == "pest"
    assert classify("how much urea") == "fertiliser"
    assert classify("mandi price of wheat") == "price"


# ---------------------------------------------------------------- platform

@pytest.fixture(scope="module")
def client(seeded):
    from sinchai_api.main import app

    with TestClient(app) as c:
        c.post("/api/demo/reset")
        yield c
        c.post("/api/demo/reset")


OP = {"Authorization": "Bearer dev-operator-token"}


def test_cluster_overview_has_three_pumps(client):
    ov = client.get("/api/cluster").json()
    ids = [p["pump_id"] for p in ov["pumps"]]
    assert ids == ["P1", "P2", "P3"]
    for p in ov["pumps"]:
        assert p["water_quality"]["restriction"] in ("none", "slight_moderate", "severe")
        assert p["health"]["status"] in ("live", "late", "silent", "stalled", "never")
    # Plots of a neighbouring pump are not on P1's twin.
    v = client.get("/api/village").json()
    assert all(f["properties"]["pump_id"] == "P1" for f in v["plots"]["features"])
    assert len(client.get("/api/village?pump=all").json()["plots"]["features"]) > len(v["plots"]["features"])


def test_silent_pump_is_flagged_after_outage(client):
    client.post("/api/demo/run_to", json={"hhmm": "11:30"})
    h = {p["pump_id"]: p["health"] for p in client.get("/api/cluster").json()["pumps"]}
    assert h["P3"]["status"] == "silent" and h["P3"]["alert"]
    assert h["P1"]["status"] in ("live", "stalled")
    client.post("/api/demo/reset")


def test_transfer_needs_confirmation_and_moves_booking(client):
    sg = client.get("/api/cluster/suggest?pump=P2").json()
    if not sg["suggestions"]:
        pytest.skip("no reachable neighbour with spare sun in this seed")
    x = sg["suggestions"][0]
    r = client.post("/api/tools/transfer_booking", json={"args": {"booking_id": x["booking_id"], "to_pump": x["to_pump"]}},
                    headers=OP).json()
    assert r["needs_confirmation"]
    r = client.post("/api/tools/transfer_booking", json={"args": {"booking_id": x["booking_id"], "to_pump": x["to_pump"]},
                                                         "confirm": True}, headers=OP).json()
    assert r["moved"] and r["to_pump"] == x["to_pump"]
    b = [b for b in client.get("/api/bookings").json() if b["id"] == x["booking_id"]][0]
    assert b["pump_id"] == x["to_pump"]
    client.post("/api/demo/reset")


def test_transfer_refuses_unreachable_pump(client):
    r = client.post("/api/tools/transfer_booking", json={"args": {"booking_id": "B0302P2001", "to_pump": "P3"},
                                                         "confirm": True}, headers=OP)
    assert r.status_code == 400


def test_passport_and_pdf(client):
    pp = client.get("/api/pumps/P1/passport").json()
    assert pp["receipts"] > 0 and pp["ledger_verified"]
    assert pp["score"]["grade"] in "ABCD"
    pdf = client.get("/api/pumps/P1/passport.pdf")
    assert pdf.status_code == 200 and pdf.content[:4] == b"%PDF"


def test_harvest_payment_through_saathi(client):
    r = client.post("/api/channels/ivr/missed_call", json={"farmer_id": "H01"}).json()
    sid = r["session_id"]
    client.post("/api/channels/ivr/say", json={"session_id": sid, "dtmf": "1"})
    r = client.post("/api/channels/ivr/missed_call", json={"farmer_id": "H01"}).json()
    r = client.post("/api/channels/ivr/say", json={"session_id": r["session_id"], "text": "फसल के बाद पैसा देब"}).json()
    assert r["pending"] and r["pending"]["tool"] == "pay_after_harvest"
    r = client.post("/api/channels/ivr/say", json={"session_id": r["session_id"], "dtmf": "1"}).json()
    assert any(c["tool"] == "pay_after_harvest" and c["confirmed"] for c in r["tool_calls"])
    bs = client.get("/api/farmers/H01").json()["bookings"]
    assert bs[-1]["paid"]
    client.post("/api/demo/reset")


def test_soil_card_sample_read_and_apply(client):
    r = client.post("/api/soil-card/read", json={"sample": True}).json()
    assert r["provider"] == "sample" and r["card"]["texture"] == "sandy loam"
    a = client.post("/api/tools/apply_soil_card", json={"args": {"farmer_id": "H01", **r["card"]}}).json()
    assert a["taw_mm_per_m"] == 130
    r = client.post("/api/soil-card/read", json={"image_b64": "aGVsbG8=", "media_type": "image/png"}).json()
    assert r.get("needs_manual_entry")


def test_recharge_and_quality_routes(client):
    r = client.get("/api/cluster/recharge").json()
    assert r["extraction_m3_per_year"] > 0 and r["cheapest"] in ("farm_pond", "recharge_shaft")
    q = client.post("/api/tools/water_quality", json={"args": {"pump_id": "P2"}}).json()
    assert q["borewell"] == "P2"
