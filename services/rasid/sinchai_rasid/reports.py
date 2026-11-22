"""Funder reports and Anudan Meter claim packs from the Rasid ledger (CSV, JSON and PDF)."""

from __future__ import annotations

import csv
import io
import json
from dataclasses import asdict
from datetime import date
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle
from sinchai_schemas import constants as C

from .ledger import Receipt, merkle_root


def summarise(receipts: list[Receipt]) -> dict:
    water = [r for r in receipts if r.kind == "water"]
    farmers = {r.farmer_ref for r in water}
    tenants = {r.farmer_ref for r in water if r.tenant}
    return {
        "receipts": len(receipts),
        "water_receipts": len(water),
        "m3": round(sum(r.m3 for r in water), 1),
        "pump_kwh": round(sum(r.kwh for r in water), 1),
        "secondary_kwh": round(sum(r.kwh for r in receipts if r.kind != "water"), 1),
        "diesel_l_avoided": round(sum(r.diesel_l_avoided for r in water), 1),
        "co2_kg_avoided": round(sum(r.co2_kg_avoided for r in water), 1),
        "farmers_served": len(farmers),
        "tenant_farmers_served": len(tenants),
        "water_revenue_rs": round(sum(r.amount_rs for r in water), 0),
        "secondary_revenue_rs": round(sum(r.amount_rs for r in receipts if r.kind != "water"), 0),
        "merkle_root": merkle_root([r.hash for r in receipts]),
        "first": receipts[0].start if receipts else None,
        "last": receipts[-1].end if receipts else None,
    }


def to_csv(receipts: list[Receipt]) -> str:
    buf = io.StringIO()
    if not receipts:
        return ""
    w = csv.DictWriter(buf, fieldnames=list(asdict(receipts[0]).keys()))
    w.writeheader()
    for r in receipts:
        w.writerow(asdict(r))
    return buf.getvalue()


def claim_pack(receipts: list[Receipt], funder: str, period_from: date, period_to: date) -> dict:
    """An Anudan Meter claim: totals, method statement, factors with sources, receipt hashes."""
    sel = [r for r in receipts if period_from.isoformat() <= r.start[:10] <= period_to.isoformat()]
    s = summarise(sel)
    return {
        "funder": funder,
        "period": [period_from.isoformat(), period_to.isoformat()],
        "totals": s,
        "method": {
            "water": "Estimated from Altivar drive power and speed via the calibrated pump curve; flow meter where fitted.",
            "diesel_counterfactual": f"{C.get('diesel_l_per_hour_5hp')} L/h for a 5 HP diesel pump delivering "
                                     f"{C.get('diesel_pump_flow_m3h')} m3/h",
            "co2_factor_kg_per_l": C.get("co2_kg_per_l_diesel"),
            "sources": {
                "diesel": C.entry("diesel_l_per_hour_5hp").source_url,
                "co2": C.entry("co2_kg_per_l_diesel").source_url,
            },
            "integrity": "SHA-256 hash chain per receipt; Merkle root over the period's receipts.",
        },
        "subsidy_equivalent_rs": round(s["diesel_l_avoided"] * C.get("bihar_diesel_subsidy_rs_per_l"), 0),
        "receipt_hashes": [r.hash for r in sel],
        "status": "Measurement-and-verification certificate (not a registered carbon credit).",
    }


def write_pdf(receipts: list[Receipt], path: Path, title: str = "SinchaiSlot funder report") -> Path:
    s = summarise(receipts)
    styles = getSampleStyleSheet()
    doc = SimpleDocTemplate(str(path), pagesize=A4, leftMargin=18 * mm, rightMargin=18 * mm)
    rows = [
        ["Water delivered", f"{s['m3']:,} m3"],
        ["Pump energy (solar)", f"{s['pump_kwh']:,} kWh"],
        ["Secondary-load energy", f"{s['secondary_kwh']:,} kWh"],
        ["Diesel avoided", f"{s['diesel_l_avoided']:,} L"],
        ["CO2 avoided", f"{s['co2_kg_avoided']:,} kg"],
        ["Farmers served (tenants)", f"{s['farmers_served']} ({s['tenant_farmers_served']})"],
        ["Receipts", f"{s['receipts']}"],
        ["Merkle root", s["merkle_root"][:32] + "..."],
    ]
    t = Table(rows, colWidths=[70 * mm, 95 * mm])
    t.setStyle(TableStyle([
        ("FONT", (0, 0), (-1, -1), "Helvetica", 10),
        ("TEXTCOLOR", (0, 0), (0, -1), colors.HexColor("#3D4A43")),
        ("LINEBELOW", (0, 0), (-1, -1), 0.25, colors.HexColor("#C8D2CC")),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
    ]))
    recent = [["Receipt", "Start", "m3", "kWh", "Diesel L", "Hash"]] + [
        [r.receipt_id, r.start[:16], f"{r.m3:.1f}", f"{r.kwh:.2f}", f"{r.diesel_l_avoided:.2f}", r.hash[:10]]
        for r in [x for x in receipts if x.kind == "water"][-25:]
    ]
    t2 = Table(recent, repeatRows=1)
    t2.setStyle(TableStyle([
        ("FONT", (0, 0), (-1, -1), "Helvetica", 8),
        ("FONT", (0, 0), (-1, 0), "Helvetica-Bold", 8),
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#E8EFEA")),
    ]))
    doc.build([
        Paragraph(title, styles["Title"]),
        Paragraph(f"Period {s['first'] or '-'} to {s['last'] or '-'}", styles["Normal"]),
        Spacer(1, 6 * mm), t, Spacer(1, 8 * mm),
        Paragraph("Latest water receipts", styles["Heading3"]), t2,
        Spacer(1, 6 * mm),
        Paragraph("Diesel counterfactual and CO2 factor as cited in the claim pack. Water estimated from "
                  "drive telemetry. Hash-chained ledger; any edit breaks verification.", styles["Italic"]),
    ])
    return path


def write_json(obj: dict, path: Path) -> Path:
    path.write_text(json.dumps(obj, indent=2, default=str))
    return path
