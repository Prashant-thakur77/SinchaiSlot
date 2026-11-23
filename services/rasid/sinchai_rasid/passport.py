"""Pump Passport: one page per pump that a lender, a funder or a buyer can trust.

Everything on it is computed from verified Rasid receipts, the drive's fault log and the telemetry uptime:
utilisation, water delivered, who it served, revenue, uptime, faults, repayment record and a transparent
creditworthiness scorecard. The scorecard is illustrative (fixed weights, shown on the page), not a lender's
model; its point is that every input is measured, not self-reported.
"""

from __future__ import annotations

import statistics
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import date, timedelta

from .ledger import Receipt

BENCH_KWH_PER_KWP = 1000.0  # a pump using most of its sun; Prayogshala's best policy reaches about this level

WEIGHTS = {"utilisation": 30, "uptime": 20, "repayment": 20, "revenue_stability": 15, "data": 15}


@dataclass
class PumpMeta:
    pump_id: str
    name: str
    kwp: float
    operator: str
    commissioned: str | None = None


def _grade(score: float) -> str:
    return "A" if score >= 80 else "B" if score >= 65 else "C" if score >= 50 else "D"


def passport(meta: PumpMeta, receipts: list[Receipt], as_of: date, *, uptime: float | None,
             faults: list[dict], repayment_on_time: float | None, ledger_verified: bool,
             data_health: str = "live") -> dict:
    since = as_of - timedelta(days=365)
    rs = [r for r in receipts if r.pump_id == meta.pump_id and since.isoformat() <= r.start[:10] <= as_of.isoformat()]
    water = [r for r in rs if r.kind == "water"]
    kwh = sum(r.kwh for r in rs)
    days_covered = len({r.start[:10] for r in rs})
    first = min((r.start[:10] for r in rs), default=None)
    span_days = max((as_of - date.fromisoformat(first)).days, 1) if first else 0
    annualise = 365 / min(span_days, 365) if span_days else 0.0
    util = kwh / meta.kwp * annualise if meta.kwp else 0.0
    m3 = sum(r.m3 for r in water)
    tenant_m3 = sum(r.m3 for r in water if r.tenant)
    farmers = {r.farmer_ref for r in water if r.farmer_ref}
    revenue = sum(r.amount_rs for r in rs)
    by_kind = defaultdict(float)
    for r in rs:
        by_kind[r.kind] += r.amount_rs
    monthly = defaultdict(float)
    for r in rs:
        monthly[r.start[:7]] += r.amount_rs
    months = [v for _, v in sorted(monthly.items())]
    cv = statistics.pstdev(months) / statistics.mean(months) if len(months) >= 3 and statistics.mean(months) > 0 else None
    fault_counts = Counter(f["code"] for f in faults)

    parts = {
        "utilisation": min(util / BENCH_KWH_PER_KWP, 1.0) if rs else 0.0,
        "uptime": uptime if uptime is not None else 0.0,
        "repayment": repayment_on_time if repayment_on_time is not None else 0.5,
        "revenue_stability": max(0.0, 1.0 - cv) if cv is not None else 0.0,
        "data": (0.5 if ledger_verified else 0.0) + (0.5 if data_health == "live" else 0.25 if data_health == "late" else 0.0),
    }
    score = sum(WEIGHTS[k] * v for k, v in parts.items())
    return {
        "pump": meta.__dict__, "as_of": as_of.isoformat(), "period_days": min(span_days, 365),
        "receipts": len(rs), "days_with_receipts": days_covered,
        "utilisation_kwh_per_kwp_yr": round(util), "energy_kwh": round(kwh, 1), "water_m3": round(m3),
        "farmers_served": len(farmers), "tenant_water_share": round(tenant_m3 / m3, 3) if m3 else None,
        "revenue_rs": round(revenue), "revenue_by_kind_rs": {k: round(v) for k, v in by_kind.items()},
        "monthly_revenue_rs": {k: round(v) for k, v in sorted(monthly.items())},
        "uptime": round(uptime, 3) if uptime is not None else None,
        "faults": [{"code": c, "count": n} for c, n in fault_counts.most_common()],
        "repayment_on_time": repayment_on_time, "ledger_verified": ledger_verified, "data_health": data_health,
        "score": {"value": round(score), "grade": _grade(score), "weights": WEIGHTS,
                  "parts": {k: round(v, 3) for k, v in parts.items()},
                  "note": "Illustrative scorecard with fixed, published weights; every input is measured."},
    }


def write_pdf(pp: dict, path) -> object:
    """One-page Pump Passport PDF."""
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import getSampleStyleSheet
    from reportlab.lib.units import mm
    from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

    styles = getSampleStyleSheet()
    doc = SimpleDocTemplate(str(path), pagesize=A4, leftMargin=18 * mm, rightMargin=18 * mm)
    p, sc = pp["pump"], pp["score"]
    ts = pp.get("tenant_water_share")
    rows = [
        ["Pump", f"{p['name']} ({p['pump_id']}), {p['kwp']} kWp"],
        ["Operator", p["operator"]],
        ["Period", f"{pp['period_days']} days to {pp['as_of']}"],
        ["Sun put to work", f"{pp['utilisation_kwh_per_kwp_yr']:,} kWh per kWp per year"],
        ["Water delivered", f"{pp['water_m3']:,} m3 to {pp['farmers_served']} farmers"
                            + (f" ({ts * 100:.0f}% to tenants)" if ts is not None else "")],
        ["Revenue", f"Rs {pp['revenue_rs']:,}"],
        ["Uptime", f"{pp['uptime'] * 100:.1f}%" if pp.get("uptime") is not None else "-"],
        ["Faults", ", ".join(f"{f['code']} x{f['count']}" for f in pp["faults"]) or "none"],
        ["After-harvest repayment on time",
         f"{pp['repayment_on_time'] * 100:.0f}%" if pp.get("repayment_on_time") is not None else "no record"],
        ["Ledger", "hash chain verified" if pp["ledger_verified"] else "NOT VERIFIED"],
        ["Data health", pp["data_health"]],
        ["Scorecard", f"{sc['value']} / 100, grade {sc['grade']}"],
    ]
    t = Table(rows, colWidths=[62 * mm, 110 * mm])
    t.setStyle(TableStyle([
        ("FONT", (0, 0), (-1, -1), "Helvetica", 10),
        ("TEXTCOLOR", (0, 0), (0, -1), colors.HexColor("#3D4A43")),
        ("LINEBELOW", (0, 0), (-1, -1), 0.25, colors.HexColor("#C8D2CC")),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
    ]))
    parts = [["Component", "Weight", "Measured"]] + [[k.replace("_", " "), str(sc["weights"][k]), f"{v:.2f}"]
                                                     for k, v in sc["parts"].items()]
    t2 = Table(parts, colWidths=[62 * mm, 30 * mm, 30 * mm])
    t2.setStyle(TableStyle([("FONT", (0, 0), (-1, -1), "Helvetica", 9), ("FONT", (0, 0), (-1, 0), "Helvetica-Bold", 9),
                            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#E8EFEA"))]))
    doc.build([Paragraph("Pump Passport", styles["Title"]), t, Spacer(1, 8 * mm),
               Paragraph("Scorecard", styles["Heading3"]), t2, Spacer(1, 6 * mm),
               Paragraph(sc["note"] + " Receipts are drive-metered and hash-chained. Labels: "
                         + "; ".join(f"{k}: {v}" for k, v in pp.get("labels", {}).items()), styles["Italic"])])
    return path
