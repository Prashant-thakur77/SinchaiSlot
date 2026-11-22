"""Platform API tests: channels, confirmation gate, agents, ledger, guards and the demo scenario."""

import pytest
from fastapi.testclient import TestClient


@pytest.fixture(scope="module")
def client(seeded):
    from sinchai_api.main import app

    with TestClient(app) as c:
        c.post("/api/demo/reset")
        yield c


def test_health_and_state(client):
    assert client.get("/health").json()["ok"]
    s = client.get("/api/state").json()
    assert s["plan_version"] >= 1 and len(s["slots"]) == 24
    assert s["forecast"]["q10"][12] <= s["forecast"]["q50"][12] <= s["forecast"]["q90"][12]


def test_missed_call_booking_needs_confirmation(client):
    r = client.post("/api/channels/ivr/missed_call", json={"farmer_id": "H01"}).json()
    assert r["pending"]["tool"] == "book_slot"
    assert not any(c["tool"] == "book_slot" and c["confirmed"] for c in r["tool_calls"])
    before = client.get("/api/farmers/H01").json()["bookings"]
    assert before == []
    r2 = client.post("/api/channels/ivr/say", json={"session_id": r["session_id"], "dtmf": "1"}).json()
    assert any(c["tool"] == "book_slot" and c["confirmed"] for c in r2["tool_calls"])
    after = client.get("/api/farmers/H01").json()["bookings"]
    assert len(after) == 1 and after[0]["m3"] > 0
    assert r2["closed"]


def test_decline_books_nothing(client):
    r = client.post("/api/channels/ivr/missed_call", json={"farmer_id": "H07"}).json()
    if r["pending"] is None:
        pytest.skip("H07 has no water need today")
    r2 = client.post("/api/channels/ivr/say", json={"session_id": r["session_id"], "text": "नहीं"}).json()
    assert r2["intent"] == "no"
    assert client.get("/api/farmers/H07").json()["bookings"] == [] or all(
        b["status"] != "confirmed" or b["id"].startswith("B0302") for b in client.get("/api/farmers/H07").json()["bookings"])


def test_tool_confirm_gate_over_http(client):
    r = client.post("/api/tools/cancel_slot", json={"args": {"farmer_id": "H01"}}).json()
    assert r["needs_confirmation"] is True


def test_operator_tools_need_token(client):
    assert client.post("/api/tools/cash_book", json={"args": {}}).status_code == 401
    ok = client.post("/api/tools/cash_book", json={"args": {}}, headers={"Authorization": "Bearer dev-operator-token"})
    assert ok.status_code == 200 and "paid_rs" in ok.json()


def test_farmer_cannot_act_for_another(client):
    from sinchai_api import tools

    with pytest.raises(tools.ToolError):
        tools.call("my_bookings", {"farmer_id": "H09"}, tools.ToolContext(role="farmer", user_ref="H01"))


def test_whatsapp_and_ussd(client):
    r = client.post("/api/channels/whatsapp", json={"farmer_id": "H03", "text": "kitna lagega?"}).json()
    assert "रुपये" in r["reply"] or "Rs" in r["reply"] or "टाका" in r["reply"] or "रुपया" in r["reply"]
    d = client.post("/api/channels/ussd/dial", json={"farmer_id": "H03"}).json()
    assert "1" in d["screen"]
    p = client.post("/api/channels/ussd/press", json={"session_id": d["session_id"], "key": "3"}).json()
    assert len(p["screen"]) <= 182


def test_ledger_verify_csv_pdf_claim(client):
    v = client.get("/api/ledger/verify").json()
    assert v["ok"] and v["checked"] > 10
    assert client.get("/api/ledger/export.csv").text.startswith("receipt_id")
    assert client.get("/api/ledger/report.pdf").content[:4] == b"%PDF"
    c = client.get("/api/ledger/claim", params={"from_date": "2024-02-01", "to_date": "2024-02-29"}).json()
    assert c["totals"]["m3"] >= 0 and "merkle_root" in c["totals"]


def test_hisaab_sql_guard(client):
    from sinchai_api.agents.hisaab import run_readonly_sql

    for bad in ("DELETE FROM ledger", "SELECT * FROM farmers", "SELECT 1; DROP TABLE ledger",
                "SELECT * FROM ledger -- x", "WITH x AS (SELECT 1) UPDATE ledger SET m3=0"):
        assert run_readonly_sql(bad).get("rejected"), bad
    ok = run_readonly_sql("SELECT kind, count(*) FROM ledger GROUP BY kind")
    assert ok["row_count"] >= 1
    a = client.post("/api/agents/hisaab", json={"text": "How much diesel did we avoid in February 2024?"}).json()
    assert "diesel" in a["answer"]


def test_copilot_guided_fault_fix(client):
    client.post("/api/drive/fault", json={"fault": "OHF"})
    assert client.get("/api/drive").json()["fault"] == "OHF"
    r = client.post("/api/agents/copilot", json={"text": "drive par OHF fault", "session_id": "cp"}).json()
    assert r["diagnosis"]["fault"] == "OHF" and r["diagnosis"]["step"] == 0
    last = None
    for k in range(1, 10):
        last = client.post("/api/agents/copilot", json={"text": "OHF fault", "session_id": "cp", "step": k}).json()
        if last["diagnosis"]["done"]:
            break
    assert last["diagnosis"]["done"]
    client.post("/api/agents/copilot", json={"text": "haan", "session_id": "cp"})
    assert client.get("/api/drive").json()["fault"] is None


def test_cloud_scenario_replans_and_calls_back(client):
    client.post("/api/demo/reset")
    s0 = client.get("/api/state").json()
    s = client.post("/api/demo/run_to", json={"hhmm": "14:10"}).json()
    assert s["cloud_applied"]
    assert s["plan_version"] > s0["plan_version"]
    assert any(d["reason"].startswith("cloud") for d in s["diffs"])
    ev = client.get("/api/events/recent", params={"kind": "nowcast"}).json()
    assert ev
    receipts = client.get("/api/events/recent", params={"kind": "receipt"}).json()
    assert receipts, "water slots before 14:00 should have produced verified receipts"
    assert client.get("/api/ledger/verify").json()["ok"]


def test_traces_recorded(client):
    t = client.get("/api/traces", params={"limit": 20}).json()
    assert t and any(x["tool_calls"] for x in t)


def test_planner_and_auditor_agents(client):
    r = client.post("/api/agents/planner", json={"text": "what if cloud 13-15 50%"}).json()
    assert "water" in r["reply"]
    a = client.post("/api/agents/auditor", json={"text": "audit"}).json()
    assert a["verify"]["ok"]
