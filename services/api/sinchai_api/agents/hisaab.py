"""Hisaab: questions over the ledger in plain language.

Offline path: a small set of question templates (Hindi and English) mapped to parameterised SQL.
LLM path (LLM_PROVIDER=anthropic): the hosted LLM writes the SQL. Either way the SQL goes through the same
guard: one statement, SELECT/WITH only, allow-listed tables, no writes or pragmas, LIMIT forced,
executed in a read-only transaction.
"""

from __future__ import annotations

import re

from sqlalchemy import text

from .. import db

FORBIDDEN = re.compile(r"\b(insert|update|delete|drop|alter|create|attach|detach|pragma|vacuum|replace|grant|"
                       r"revoke|truncate|copy|call|exec|execute|into|set)\b", re.I)
TABLE_REF = re.compile(r"\b(?:from|join)\s+([a-zA-Z_][a-zA-Z0-9_]*)", re.I)
MAX_ROWS = 200

SCHEMA = (
    "ledger(seq, receipt_id, kind[water|mill|chaff|battery], booking_id, pump_id, plot_id, farmer_ref, tenant, "
    "start ISO text, end, kwh, m3, amount_rs, diesel_l_avoided, co2_kg_avoided); "
    "bookings(id, farmer_id, plot_id, pump_id, day, slot_start, slot_end, m3_requested, m3_delivered, price_rs, "
    "status, channel, paid); plots(id, farmer_id, area_ha, crop, stage, need_m3); pumps(id, name, kwp); "
    "sellers(id, kind, rate_rs_per_h, flow_m3h, agent_bookings)"
)


class SqlRejected(ValueError):
    pass


def guard(sql: str) -> str:
    s = sql.strip().rstrip(";").strip()
    if ";" in s:
        raise SqlRejected("only one statement is allowed")
    if not re.match(r"^(select|with)\b", s, re.I):
        raise SqlRejected("only SELECT queries are allowed")
    if FORBIDDEN.search(s):
        raise SqlRejected("write or admin keywords are not allowed")
    if "--" in s or "/*" in s:
        raise SqlRejected("comments are not allowed")
    ctes = {m.lower() for m in re.findall(r"\b([a-zA-Z_][a-zA-Z0-9_]*)\s+as\s*\(", s, re.I)}
    tables = {t.lower() for t in TABLE_REF.findall(s)} - ctes
    bad = tables - db.ANALYST_TABLES
    if bad:
        raise SqlRejected(f"table not allowed: {', '.join(sorted(bad))}")
    if not re.search(r"\blimit\s+\d+\s*$", s, re.I):
        s = f"SELECT * FROM ({s}) AS q LIMIT {MAX_ROWS}"
    return s


def run_readonly_sql(sql: str) -> dict:
    try:
        safe = guard(sql)
    except SqlRejected as e:
        return {"error": str(e), "rejected": True}
    eng = db.engine()
    with eng.connect() as c:
        if eng.dialect.name == "postgresql":
            c.execute(text("SET TRANSACTION READ ONLY"))
        elif eng.dialect.name == "sqlite":
            c.exec_driver_sql("PRAGMA query_only = ON")
        try:
            res = c.execute(text(safe))
            cols = list(res.keys())
            rows = [[float(x) if hasattr(x, "is_finite") else x for x in r] for r in res.fetchmany(MAX_ROWS)]
        except Exception as e:  # noqa: BLE001 - report query errors to the asker instead of failing the request
            return {"error": f"query failed: {str(e).splitlines()[0][:200]}", "sql": safe}
        finally:
            if eng.dialect.name == "sqlite":
                c.exec_driver_sql("PRAGMA query_only = OFF")
            c.rollback()
    return {"sql": safe, "columns": cols, "rows": rows, "row_count": len(rows)}


MONTHS = {"jan": "01", "feb": "02", "mar": "03", "apr": "04", "may": "05", "jun": "06", "jul": "07", "aug": "08",
          "sep": "09", "oct": "10", "nov": "11", "dec": "12", "जनवरी": "01", "फरवरी": "02", "मार्च": "03"}


def _month(q: str) -> str | None:
    ql = q.lower()
    for k, v in MONTHS.items():
        if k in ql:
            y = re.search(r"(20\d\d)", ql)
            return f"{y.group(1) if y else '2024'}-{v}"
    return None


def template_sql(question: str) -> tuple[str, str] | None:
    q = question.lower()
    month = _month(question)
    where = f"WHERE kind = 'water' AND substr(start, 1, 7) = '{month}'" if month else "WHERE kind = 'water'"
    if any(k in q for k in ("diesel", "डीजल", "डीज़ल")):
        return (f"SELECT round(CAST(sum(diesel_l_avoided) AS numeric), 1) AS diesel_l_avoided, round(CAST(sum(co2_kg_avoided) AS numeric), 1) AS co2_kg "
                f"FROM ledger {where}", "diesel")
    if any(k in q for k in ("co2", "carbon", "कार्बन")):
        return f"SELECT round(CAST(sum(co2_kg_avoided) AS numeric), 1) AS co2_kg_avoided FROM ledger {where}", "co2"
    if any(k in q for k in ("tenant", "बटाईदार", "किरायेदार")):
        return (f"SELECT tenant, count(DISTINCT farmer_ref) AS farmers, round(CAST(sum(m3) AS numeric), 1) AS m3 FROM ledger {where} "
                f"GROUP BY tenant", "tenants")
    if any(k in q for k in ("mill", "चक्की", "battery", "बैटरी", "secondary")):
        cond = f"AND substr(start, 1, 7) = '{month}'" if month else ""
        return (f"SELECT kind, round(CAST(sum(kwh) AS numeric), 1) AS kwh, round(CAST(sum(amount_rs) AS numeric), 0) AS revenue_rs FROM ledger "
                f"WHERE kind != 'water' {cond} GROUP BY kind", "secondary")
    if any(k in q for k in ("revenue", "income", "कमाई", "आमदनी", "पैसा")):
        cond = f"WHERE substr(start, 1, 7) = '{month}'" if month else ""
        return f"SELECT kind, round(CAST(sum(amount_rs) AS numeric), 0) AS revenue_rs FROM ledger {cond} GROUP BY kind", "revenue"
    if any(k in q for k in ("water", "पानी", "m3", "litre", "लीटर")):
        return (f"SELECT round(CAST(sum(m3) AS numeric), 1) AS m3, round(CAST(sum(m3) * 1000 AS numeric), 0) AS litres, count(*) AS receipts "
                f"FROM ledger {where}", "water")
    if any(k in q for k in ("daily", "per day", "रोज")):
        return (f"SELECT substr(start, 1, 10) AS day, round(CAST(sum(m3) AS numeric), 1) AS m3 FROM ledger {where} GROUP BY day "
                f"ORDER BY day", "daily")
    if any(k in q for k in ("farmer", "किसान", "served")):
        return f"SELECT count(DISTINCT farmer_ref) AS farmers_served FROM ledger {where}", "farmers"
    return None


def answer(question: str) -> dict:
    from . import runtime

    sql, kind = None, None
    t = template_sql(question)
    if t:
        sql, kind = t
    elif runtime.anthropic_available():
        sql = llm_sql(question)
        kind = "llm"
    if not sql:
        return {"answer": "I can answer questions on water, diesel, CO2, tenants, revenue, mill and battery use, "
                          "by month. Try: 'How much diesel did we avoid in February 2024?'", "sql": None}
    res = run_readonly_sql(sql)
    if "error" in res:
        return {"answer": f"Query rejected: {res['error']}", "sql": sql}
    return {"answer": _phrase(kind, res), "sql": res["sql"], "columns": res["columns"], "rows": res["rows"],
            "chart": kind in ("daily", "tenants", "secondary", "revenue")}


def _phrase(kind: str, res: dict) -> str:
    r = res["rows"]
    if not r:
        return "No receipts match."
    row = dict(zip(res["columns"], r[0], strict=False))
    if kind == "diesel":
        return f"{row['diesel_l_avoided']} litres of diesel avoided ({row['co2_kg']} kg CO2), from verified receipts."
    if kind == "co2":
        return f"{row['co2_kg_avoided']} kg of CO2 avoided, from verified receipts."
    if kind == "water":
        return f"{row['m3']} m3 ({int(row['litres'] or 0):,} litres) of solar water over {row['receipts']} receipts."
    if kind == "farmers":
        return f"{row['farmers_served']} farmers received solar water."
    return f"{len(r)} rows."


def llm_sql(question: str) -> str | None:
    import anthropic

    from ..settings import settings

    client = anthropic.Anthropic()
    resp = client.beta.messages.create(
        model=settings().anthropic_model, max_tokens=16000, output_config={"effort": "low"},
        betas=["server-side-fallback-2026-07-01"], fallbacks="default",
        system=("Write one SQLite SELECT that answers the question over this schema: " + SCHEMA +
                " Reply with the SQL only, no prose, no code fences."),
        messages=[{"role": "user", "content": f"<question>{question[:500]}</question>"}],
    )
    if resp.stop_reason == "refusal":
        return None
    return " ".join(b.text for b in resp.content if b.type == "text").strip().strip("`")
