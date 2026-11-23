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
        s.query(db.Credit).filter(~db.Credit.booking_id.like("HIST-%")).delete(synchronize_session=False)
        s.query(db.Plot).update({db.Plot.taw_mm_per_m: None, db.Plot.soil_card: None}, synchronize_session=False)
        s.query(db.Issue).delete()
        s.query(db.Maintenance).filter(db.Maintenance.note.notlike("%(simulated history)")).delete(synchronize_session=False)
        s.commit()


def _with_persistence_fill(pv_act, fc):
    """Archived multi-model forecasts start in 2024. Seeded ledger history before that is planned on a
    persistence forecast (yesterday's sun, widened band) so the year of receipts is complete; the proof's
    held-out years never use this fill."""
    import pandas as pd

    persist = pv_act.shift(24)
    missing = persist.index[(persist.index < fc.index.min())]
    if len(missing) == 0:
        return fc
    p = persist.reindex(missing).fillna(0)
    fill = pd.DataFrame({"q10": p * 0.6, "q50": p, "q90": p * 1.2}, index=missing)
    return pd.concat([fill, fc[["q10", "q50", "q90"]]]).sort_index()


def _seed_history_extras(s, day: date) -> None:
    """SIMULATED operating history for the Pump Passport and harvest-linked repayment: logged faults with
    downtime, and after-harvest credits from the last two seasons (most repaid on time, a few late)."""
    import random

    rng = random.Random(7)
    faults = {"P1": [("OHF", 3.0), ("ULF", 1.5), ("OSF", 0.5)], "P2": [("ULF", 4.0), ("ULF", 3.0), ("OHF", 6.0), ("PHF", 2.0)],
              "P3": [("OHF", 2.0)]}
    for pid, fl in faults.items():
        for j, (code, dh) in enumerate(fl):
            when = datetime.combine(day - timedelta(days=30 + 41 * j + rng.randint(0, 20)), datetime.min.time())
            s.add(db.Maintenance(pump_id=pid, action="fault cleared", note=f"{code} cleared by the Saur Mitra (simulated history)",
                                 fault=code, downtime_h=dh, created_at=when + timedelta(hours=11)))
    farmers = s.query(db.Farmer).filter(db.Farmer.tenant.is_(True)).all()
    for f in farmers:
        if rng.random() > 0.45 and f.id != RAMESH_ID:
            continue
        pid = f.id[:2] if f.id.startswith("P") else "P1"
        for season_end, due in ((date(2023, 4, 25), date(2023, 5, 2)), (date(2023, 11, 20), date(2023, 11, 27))):
            amt = float(rng.choice([150, 200, 250, 300]))
            late = f.id != RAMESH_ID and rng.random() < 0.12
            paid = due + timedelta(days=rng.randint(8, 30)) if late else due - timedelta(days=rng.randint(0, 6))
            s.add(db.Credit(farmer_id=f.id, booking_id=f"HIST-{f.id}-{due:%y%m}", pump_id=pid, amount_rs=amt,
                            fee_rs=round(amt * C.get("harvest_credit_fee_rate") * 75 / 365), due=due.isoformat(),
                            paid_on=paid.isoformat(), created_on=(season_end - timedelta(days=75)).isoformat()))
    s.commit()


PUMPS = [  # (pump id, village seed, name, operator)
    ("P1", 0, "Chakhaji Saur Pump 1 (simulated)", "Sunita Kumari (Saur Mitra)"),
    ("P2", 1, "Chakhaji Saur Pump 2 (simulated)", "Kiran Kumari (Saur Mitra)"),
    ("P3", 2, "Chakhaji Saur Pump 3 (simulated)", "Pinki Kumari (Saur Mitra)"),
]



def _relabel(vil, pid: str, dlon: float, dlat: float) -> None:
    """Give a neighbouring pump's village its own ids and move it to that pump's command area."""
    if pid == "P1":
        return
    for h in vil.households:
        h.id = f"{pid}{h.id}"
        h.plots = [f"{pid}{x}" for x in h.plots]
    for p in vil.plots:
        p.id, p.household = f"{pid}{p.id}", f"{pid}{p.household}"
        p.lon, p.lat = p.lon + dlon, p.lat + dlat


def _pump_history(pid: str, vseed: int, ledger_from: date, day: date) -> list[Receipt]:
    """Run SinchaiSlot (policy D) on one pump's village up to the day before the demo; its receipts.
    Runs in a worker process so the three pumps simulate in parallel."""
    offsets = C.get("cluster_pump_offsets_deg")
    dlon, dlat = offsets.get(pid, (0.0, 0.0))
    vil = make_village(vseed)
    _relabel(vil, pid, dlon, dlat)
    pv_act = simdata.pv_actual()
    pv_fc = _with_persistence_fill(pv_act, simdata.forecast_pv())
    reqs = demand_trace(vil, simdata.daily_weather(), ledger_from, day + timedelta(days=10))
    tariff = C.get("sinchaislot_tariff_rs_per_m3")
    h_from = ledger_from
    out: list[Receipt] = []
    # Ledger history: run SinchaiSlot (policy D) on this pump's village up to the day before the demo.
    yd = E.build_year_data(pv_act, pv_fc, h_from, day - timedelta(days=1))
    hist_reqs = [r for r in reqs if r.day < day]
    st = E.run_year(P.SinchaiSlot(), vil, hist_reqs, yd, with_budget=True)
    req_by_id = {r.id: r for r in hist_reqs}
    for log in st.slot_log:
        r = req_by_id.get(log["req"])
        if r is None or log["m3"] <= 0.01:
            continue
        h = E.SLOT_HOURS[log["slot"]]
        start = datetime.combine(log["day"], datetime.min.time()) + timedelta(hours=h, minutes=30)
        end = start + timedelta(hours=1)
        out.append(make_water_receipt("", r.id, pid, r.plot, r.household, r.tenant,
                                      start.isoformat(timespec="minutes"), end.isoformat(timespec="minutes"),
                                      log["kwh"], log["m3"], tariff if not r.owner else 0.0))
    for d in st.daily:
        dd = d["day"]
        for kind, kwh, qty, amount in (
            ("mill", d.get("mill_kwh", 0), d.get("mill_kg", 0), d.get("mill_kg", 0) * C.get("mill_rs_per_kg")),
            ("chaff", d.get("chaff_kwh", 0), d.get("chaff_h", 0),
             d.get("chaff_h", 0) * C.get("chaff_cutter_rs_per_hour")),
            ("battery", d.get("battery_kwh", 0), d.get("battery_kwh", 0) / C.get("battery_pack_kwh"),
             d.get("battery_kwh", 0) / C.get("battery_pack_kwh") * C.get("battery_pack_rs_per_charge")),
        ):
            if kwh <= 0.01:
                continue
            out.append(Receipt(
                receipt_id="", kind=kind, booking_id=None, pump_id=pid, plot_id=None, farmer_ref=None,
                tenant=None, start=f"{dd.isoformat()}T07:00", end=f"{dd.isoformat()}T17:00", kwh=round(kwh, 3),
                m3=0.0, quantity=round(qty, 2), amount_rs=round(amount, 2), method="drive-energy"))
    return out


def seed(ledger_from: date = date(2023, 3, 1), verbose: bool = True) -> dict:
    db.reset_engine()
    db.init_db(drop=True)
    proof = load_proof()
    day = date.fromisoformat(proof["demo_day"]["date"])
    dw = simdata.daily_weather()
    offsets = C.get("cluster_pump_offsets_deg")
    tariff = C.get("sinchaislot_tariff_rs_per_m3")
    history: list[Receipt] = []
    n_farmers = n_plots = 0

    from concurrent.futures import ProcessPoolExecutor

    pool = ProcessPoolExecutor(max_workers=len(PUMPS))
    jobs = [pool.submit(_pump_history, pid, vseed, ledger_from, day) for pid, vseed, _, _ in PUMPS]
    with db.session() as s:
        for k_pump, (pid, vseed, pname, operator) in enumerate(PUMPS):
            dlon, dlat = offsets.get(pid, (0.0, 0.0))
            vil = make_village(vseed)
            _relabel(vil, pid, dlon, dlat)
            h_from = ledger_from
            reqs = demand_trace(vil, dw, h_from, day + timedelta(days=10))
            s.add(db.Pump(id=pid, name=pname, kwp=C.get("pv_kwp"), lon=C.get("site_lon") + dlon,
                          lat=C.get("site_lat") + dlat, operator=operator))
            for i, h in enumerate(vil.households):
                is_r = h.id == RAMESH_ID
                s.add(db.Farmer(id=h.id, display_name=NAMES[(i + 17 * k_pump) % len(NAMES)],
                                phone_hash=phone_hash(i + 100 * k_pump),
                                language="mai" if is_r else h.language, tenant=True if is_r else h.tenant,
                                owner=h.owner, balance_rs=0.0))
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
                s.add(db.Plot(id=p.id, farmer_id=p.household, pump_id=pid, area_ha=round(p.area_ha, 4), crop=crop,
                              stage=stage, lon=p.lon, lat=p.lat, geojson=plot_square(p.lon, p.lat, p.area_ha),
                              need_m3=round(need, 1)))
            n_farmers += len(vil.households)
            n_plots += len(vil.plots)
            s.commit()

            # Demo-day bookings: the FAO-56 requests falling due around the demo day (Ramesh books live).
            n = 0
            prefix = "" if pid == "P1" else pid
            for r in reqs:
                if not (day - timedelta(days=1) <= r.day <= day + timedelta(days=2)) or r.household == RAMESH_ID:
                    continue
                n += 1
                s.add(db.Booking(id=f"B{day:%m%d}{prefix}{n:03d}", farmer_id=r.household, plot_id=r.plot, pump_id=pid,
                                 day=day.isoformat(), m3_requested=round(r.gross_m3, 1),
                                 price_rs=round(r.gross_m3 * tariff, 0),
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

        _seed_history_extras(s, day)

        for j in jobs:
            history.extend(j.result())
        pool.shutdown()

        # One hash chain for the cluster, in time order.
        history.sort(key=lambda r: (r.start, r.pump_id, r.kind, r.booking_id or ""))
        for k, rec in enumerate(history, start=1):
            rec.receipt_id = f"R{k:06d}"
        ledger_service.append_many(s, history)
        n_ledger = s.query(db.LedgerRow).count()
        n_book = s.query(db.Booking).count()
        save_snapshot(s)
    db.refresh_geometry()
    out = {"demo_day": day.isoformat(), "pumps": len(PUMPS), "farmers": n_farmers, "plots": n_plots,
           "bookings": n_book, "ledger_rows": n_ledger, "label": "SIMULATED village on REAL weather"}
    if verbose:
        print(out)
    return out


def main() -> None:
    seed()


if __name__ == "__main__":
    main()
