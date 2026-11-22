"""`make seed`: build the demo database from Prayogshala village 0 (SIMULATED) on real weather.

* farmers, plots and crops from the synthetic village (names are fictional)
* plot need from the FAO-56 water balance on real NASA POWER weather
* the demo day's bookings from that day's FAO-56 irrigation requests
* the Rasid ledger history from running policy D (SinchaiSlot) on 2024-01-01 .. the day before the demo
* Paani Khata sellers (diesel / electric pump owners) around the cluster
"""

from __future__ import annotations

import hashlib
import math
from datetime import date, datetime, timedelta

from sinchai_planner import fao56
from sinchai_rasid.ledger import Receipt, make_water_receipt
from sinchai_schemas import constants as C
from sinchai_sim import data as simdata
from sinchai_sim import engine as E
from sinchai_sim import policies as P
from sinchai_sim.village import demand_trace, make_village

from . import db, ledger_service
from .settings import settings
from .state import load_proof

# Fictional names for the synthetic households (no real persons).
NAMES = [
    "Mahesh Yadav", "Ramesh Sahni", "Gita Devi", "Suresh Paswan", "Kavita Kumari", "Dinesh Mandal", "Anita Devi",
    "Rajesh Ram", "Sunil Mahto", "Pooja Kumari", "Manoj Thakur", "Rekha Devi", "Ajay Paswan", "Sarita Devi",
    "Vinod Sahni", "Meena Kumari", "Arun Yadav", "Lalita Devi", "Santosh Ram", "Usha Devi", "Pappu Mandal",
    "Kiran Kumari", "Ashok Mahto", "Sunita Kumari", "Ravi Paswan", "Mamta Devi", "Pramod Yadav", "Sangita Devi",
    "Mukesh Sahni", "Babita Kumari", "Naresh Ram", "Shanti Devi", "Umesh Thakur", "Rinku Kumari", "Kamlesh Yadav",
    "Savitri Devi", "Bablu Paswan", "Manju Devi", "Shankar Mahto", "Pinki Kumari", "Raju Sahni", "Phool Devi",
    "Dilip Mandal", "Asha Devi", "Sanjay Ram", "Nirmala Devi", "Bhola Yadav", "Radha Devi", "Gopal Paswan",
    "Sushila Devi",
]
RAMESH_ID = "H01"
LANG_NAMES = {"mai": "Maithili", "hi": "Hindi", "bho": "Bhojpuri", "en": "English"}


def phone_hash(i: int) -> str:
    # Synthetic numbers only; stored salted and hashed, never in clear.
    return hashlib.sha256(f"{settings().edge_secret}|+91900000{i:04d}".encode()).hexdigest()


def plot_square(lon: float, lat: float, area_ha: float) -> dict:
    side_m = math.sqrt(area_ha * 10_000)
    dlat = side_m / 2 / 111_320
    dlon = side_m / 2 / (111_320 * math.cos(math.radians(lat)))
    ring = [[lon - dlon, lat - dlat], [lon + dlon, lat - dlat], [lon + dlon, lat + dlat], [lon - dlon, lat + dlat],
            [lon - dlon, lat - dlat]]
    return {"type": "Polygon", "coordinates": [ring]}


def crop_on(plot, day: date) -> tuple[str, str]:
    """(crop, stage) growing on a plot on a given day, from its season crops."""
    for y in (day.year - 1, day.year):
        seasons = plot.crops.get(y, {})
        for season in ("rabi", "zaid", "kharif"):
            key = seasons.get(season)
            if not key or key == "fallow":
                continue
            c = fao56.CROPS[key]
            das = (day - c.sowing_date(y)).days
            if 0 <= das < c.length:
                return key, fao56.stage_name(c, das)
    return "fallow", "-"


SNAPSHOT_COLS = ("id", "farmer_id", "plot_id", "pump_id", "day", "m3_requested", "price_rs", "status", "channel", "paid")


def save_snapshot(s) -> None:
    """Remember the seeded state so a demo reset can restore it exactly (demo mode only)."""
    snap = {
        "ledger_seq": max([r.seq for r in s.query(db.LedgerRow).all()] or [0]),
        "bookings": [{c: getattr(b, c) for c in SNAPSHOT_COLS} for b in s.query(db.Booking).all()],
        "balances": {f.id: f.balance_rs for f in s.query(db.Farmer).all()},
    }
    s.merge(db.Memory(farmer_id="H00", key="__demo_snapshot__", value=snap))
    s.commit()


def restore_snapshot() -> None:
    with db.session() as s:
        m = s.get(db.Memory, ("H00", "__demo_snapshot__"))
        if m is None:
            return
        snap = m.value
        s.query(db.LedgerRow).filter(db.LedgerRow.seq > snap["ledger_seq"]).delete()
        s.query(db.Booking).delete()
        for b in snap["bookings"]:
            s.add(db.Booking(**b))
        for fid, bal in snap["balances"].items():
            f = s.get(db.Farmer, fid)
            if f is not None:
                f.balance_rs = bal
        s.query(db.Memory).filter(db.Memory.key != "__demo_snapshot__").delete()
        s.commit()


def seed(ledger_from: date = date(2024, 1, 1), verbose: bool = True) -> dict:
    db.reset_engine()
    db.init_db(drop=True)
    proof = load_proof()
    day = date.fromisoformat(proof["demo_day"]["date"])
    vil = make_village(0)
    dw = simdata.daily_weather()
    reqs = demand_trace(vil, dw, ledger_from, day + timedelta(days=10))

    with db.session() as s:
        s.add(db.Pump(id="P1", name="Chakhaji Saur Pump 1 (simulated)", kwp=C.get("pv_kwp"), lon=C.get("site_lon"),
                      lat=C.get("site_lat"), operator="Sunita Kumari (Saur Mitra)"))
        for i, h in enumerate(vil.households):
            s.add(db.Farmer(id=h.id, display_name=NAMES[i % len(NAMES)], phone_hash=phone_hash(i),
                            language=h.language if h.id != RAMESH_ID else "mai", tenant=h.tenant if h.id != RAMESH_ID else True, owner=h.owner,
                            balance_rs=0.0))
        for p in vil.plots:
            crop, stage = crop_on(p, day)
            if p.household == RAMESH_ID:
                # Persona: Ramesh, tenant on about half an acre of wheat at grain filling.
                crop, stage = "wheat", "mid"
                p.area_ha = 0.2
            upcoming = [r for r in reqs if r.plot == p.id and day - timedelta(days=2) <= r.day <= day + timedelta(days=3)]
            need = upcoming[0].gross_m3 if upcoming else 0.0
            if p.household == RAMESH_ID:
                # Ramesh's wheat at grain filling: 50 mm net (below FAO-56 RAW for wheat, ~82 mm on loam).
                need = fao56.gross_m3(50, p.area_ha, C.get("application_efficiency"))
            s.add(db.Plot(id=p.id, farmer_id=p.household, area_ha=round(p.area_ha, 4), crop=crop, stage=stage,
                          lon=p.lon, lat=p.lat, geojson=plot_square(p.lon, p.lat, p.area_ha), need_m3=round(need, 1)))
        s.commit()

        # Demo-day bookings: the FAO-56 requests falling due around the demo day (Ramesh books live).
        n = 0
        for r in reqs:
            if not (day - timedelta(days=1) <= r.day <= day + timedelta(days=2)) or r.household == RAMESH_ID:
                continue
            n += 1
            s.add(db.Booking(id=f"B{day:%m%d}{n:03d}", farmer_id=r.household, plot_id=r.plot, pump_id="P1",
                             day=day.isoformat(), m3_requested=round(r.gross_m3, 1),
                             price_rs=round(r.gross_m3 * C.get("sinchaislot_tariff_rs_per_m3"), 0),
                             status="paid" if n % 4 else "confirmed", paid=bool(n % 4),
                             channel=["ivr", "whatsapp", "mitra", "ussd"][n % 4]))
        s.commit()

        # Paani Khata sellers.
        sellers = [("S1", "Bhola Yadav (diesel)", "diesel", 120, 30), ("S2", "Raju Sahni (diesel)", "diesel", 130, 28),
                   ("S3", "Gopal Paswan (diesel)", "diesel", 120, 30), ("S4", "Ashok Mahto (electric)", "electric", 90, 25)]
        for k, (sid, nm, kind, rate, flow) in enumerate(sellers):
            ang = k * 1.6
            s.add(db.Seller(id=sid, display_name=nm, kind=kind, rate_rs_per_h=rate, flow_m3h=flow,
                            lon=C.get("site_lon") + 0.006 * math.cos(ang), lat=C.get("site_lat") + 0.005 * math.sin(ang)))
        s.commit()

        # Ledger history: run SinchaiSlot (policy D) on village 0 up to the day before the demo.
        yd = E.build_year_data(simdata.pv_actual(), simdata.forecast_pv(), ledger_from, day - timedelta(days=1))
        hist_reqs = [r for r in reqs if r.day < day]
        st = E.run_year(P.SinchaiSlot(), vil, hist_reqs, yd, with_budget=True)
        req_by_id = {r.id: r for r in hist_reqs}
        tariff = C.get("sinchaislot_tariff_rs_per_m3")
        k = 0
        for log in st.slot_log:
            r = req_by_id.get(log["req"])
            if r is None or log["m3"] <= 0.01:
                continue
            k += 1
            h = E.SLOT_HOURS[log["slot"]]
            start = datetime.combine(log["day"], datetime.min.time()) + timedelta(hours=h, minutes=30)
            end = start + timedelta(hours=1)
            rec = make_water_receipt(f"R{k:06d}", r.id, "P1", r.plot, r.household, r.tenant,
                                     start.isoformat(timespec="minutes"), end.isoformat(timespec="minutes"),
                                     log["kwh"], log["m3"], tariff if not r.owner else 0.0)
            ledger_service.append(s, rec)
        for d in st.daily:
            dd = d["day"]
            for kind, kwh, qty, amount in (
                ("mill", d.get("mill_kwh", 0), d.get("mill_kg", 0), d.get("mill_kg", 0) * C.get("mill_rs_per_kg")),
                ("chaff", d.get("chaff_kwh", 0), d.get("chaff_h", 0), d.get("chaff_h", 0) * C.get("chaff_cutter_rs_per_hour")),
                ("battery", d.get("battery_kwh", 0), d.get("battery_kwh", 0) / C.get("battery_pack_kwh"),
                 d.get("battery_kwh", 0) / C.get("battery_pack_kwh") * C.get("battery_pack_rs_per_charge")),
            ):
                if kwh <= 0.01:
                    continue
                k += 1
                ledger_service.append(s, Receipt(
                    receipt_id=f"R{k:06d}", kind=kind, booking_id=None, pump_id="P1", plot_id=None, farmer_ref=None,
                    tenant=None, start=f"{dd.isoformat()}T07:00", end=f"{dd.isoformat()}T17:00", kwh=round(kwh, 3),
                    m3=0.0, quantity=round(qty, 2), amount_rs=round(amount, 2), method="drive-energy"))
        n_ledger = s.query(db.LedgerRow).count()
        n_book = s.query(db.Booking).count()
        save_snapshot(s)
    out = {"demo_day": day.isoformat(), "farmers": len(vil.households), "plots": len(vil.plots), "bookings": n_book,
           "ledger_rows": n_ledger, "label": "SIMULATED village on REAL weather"}
    if verbose:
        print(out)
    return out


def main() -> None:
    seed()


if __name__ == "__main__":
    main()
