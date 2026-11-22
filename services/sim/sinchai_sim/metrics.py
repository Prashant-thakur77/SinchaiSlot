"""Metrics for one simulated year (PLAN.md 7.3). Every published number is computed here."""

from __future__ import annotations

import numpy as np
import pandas as pd
from sinchai_planner import fao56
from sinchai_schemas import constants as C

from .engine import State


def gini(x: np.ndarray) -> float:
    x = np.sort(np.asarray(x, dtype=float))
    if len(x) == 0 or x.sum() == 0:
        return 0.0
    n = len(x)
    return float((2 * np.arange(1, n + 1) - n - 1).dot(x) / (n * x.sum()))


def year_metrics(st: State, policy_name: str) -> dict:
    cfg = st.cfg
    d = pd.DataFrame(st.daily)
    done = st.done
    kwp = cfg.pv_kwp
    useful = float(d["useful_kwh"].sum())
    pv = float(d["pv_kwh"].sum())
    solar_m3 = sum(p.solar_m3 for p in done)
    pumped_m3 = sum(p.pumped_m3 for p in done)
    diesel_m3 = sum(p.diesel_m3 for p in done)
    need_m3 = sum(p.req.gross_m3 for p in done)
    diesel_l_avoided = solar_m3 / cfg.diesel_flow_m3h * cfg.diesel_l_per_h
    co2 = diesel_l_avoided * cfg.co2_per_l

    buyers = [p for p in done if not p.req.owner]
    buyer_m3 = sum(p.solar_m3 + p.diesel_m3 for p in buyers)
    buyer_paid = sum(p.paid_rs for p in buyers)
    solar_buyers = [p for p in buyers if p.solar_m3 > 0]
    solar_paid = sum(p.paid_rs - p.diesel_m3 * cfg.diesel_rs_per_m3 for p in solar_buyers)
    solar_buyer_m3 = sum(p.solar_m3 for p in solar_buyers)

    waits = np.array([(p.first_water - p.req.day).days for p in done if p.first_water is not None and p.solar_m3 > 0])
    tenants = [p for p in done if p.req.tenant]
    tenant_need = sum(p.req.gross_m3 for p in tenants)
    tenant_solar = sum(p.solar_m3 for p in tenants)

    hh_need: dict[str, float] = {}
    hh_solar: dict[str, float] = {}
    for p in done:
        hh_need[p.req.household] = hh_need.get(p.req.household, 0) + p.req.gross_m3
        hh_solar[p.req.household] = hh_solar.get(p.req.household, 0) + p.solar_m3
    share = np.array([hh_solar[h] / hh_need[h] for h in hh_need if hh_need[h] > 0])

    # Water productivity on cereals: m3 applied per kg grain.
    plot_area = {p.id: p.area_ha for p in st.village.plots}
    cereal_m3 = sum(p.pumped_m3 + p.diesel_m3 for p in done if p.req.crop in ("wheat", "maize", "paddy"))
    cereal_area_yield = {}
    for p in done:
        if p.req.crop in ("wheat", "maize", "paddy"):
            key = (p.req.plot, p.req.crop)
            cereal_area_yield[key] = plot_area[p.req.plot] * fao56.CROPS[p.req.crop].yield_t_per_ha * 1000
    grain_kg = sum(cereal_area_yield.values())
    area_acres = st.village.area_ha / 0.404686

    # Revenue.
    water_rev = sum(p.paid_rs - p.diesel_m3 * cfg.diesel_rs_per_m3 for p in buyers)
    mill_rev = float(d.get("mill_kg", pd.Series([0])).sum()) * cfg.mill_rs_per_kg
    chaff_rev = float(d.get("chaff_h", pd.Series([0])).sum()) * cfg.chaff_rs_per_h
    batt_rev = float(d.get("battery_kwh", pd.Series([0])).sum()) / cfg.pack_kwh * cfg.pack_rs
    revenue = water_rev + mill_rev + chaff_rev + batt_rev
    owner_own_m3 = sum(p.solar_m3 for p in done if p.req.owner)
    owner_saving = owner_own_m3 * cfg.diesel_rs_per_m3
    om = C.get("om_rs_per_year")
    if policy_name.startswith("D"):
        mitra = revenue * C.get("saur_mitra_revenue_share")
        platform = revenue * C.get("platform_revenue_share")
    elif policy_name.startswith("C"):
        mitra = revenue * C.get("saur_mitra_revenue_share")
        platform = 0.0
    else:
        mitra = platform = 0.0
    owner_income = revenue - mitra - platform - om + owner_saving
    capex = C.get("unit_capex_rs")

    budget_cap = None
    if st.budget is not None:
        budget_cap = st.budget.annual_m3
    from sinchai_jal.budget import WaterBudget
    ref_budget = WaterBudget.for_cluster(command_area_ha=st.village.area_ha)

    # Seasonal extraction vs the budget, for policies that do not enforce it.
    dd = d.copy()
    dd["day"] = pd.to_datetime(dd["day"])
    season = dd["day"].dt.month.map(lambda m: "rabi" if m in (11, 12, 1, 2) else ("zaid" if m in (3, 4, 5, 6) else "kharif"))
    seasonal = dd.groupby(season)["water_m3"].sum().to_dict()
    exceeded = {s: bool(v > ref_budget.season_cap(s) + 1e-6) for s, v in seasonal.items()}

    return {
        "policy": policy_name,
        "utilisation_kwh_per_kwp": round(useful / kwp, 1),
        "solar_share_used": round(useful / pv, 4) if pv else 0.0,
        "pv_available_kwh": round(pv, 1),
        "useful_kwh": round(useful, 1),
        "pump_kwh": round(float(d["pump_kwh"].sum()), 1),
        "mill_kwh": round(float(d.get("mill_kwh", pd.Series([0])).sum()), 1),
        "chaff_kwh": round(float(d.get("chaff_kwh", pd.Series([0])).sum()), 1),
        "battery_kwh": round(float(d.get("battery_kwh", pd.Series([0])).sum()), 1),
        "mill_kg": round(float(d.get("mill_kg", pd.Series([0])).sum()), 1),
        "solar_m3": round(solar_m3, 1),
        "pumped_m3": round(pumped_m3, 1),
        "over_application_m3": round(pumped_m3 - solar_m3, 1),
        "diesel_m3": round(diesel_m3, 1),
        "need_m3": round(need_m3, 1),
        "solar_share_of_need": round(solar_m3 / need_m3, 4) if need_m3 else 0.0,
        "diesel_l_avoided": round(diesel_l_avoided, 1),
        "co2_kg_avoided": round(co2, 1),
        "farmer_rs_per_m3_all_sources": round(buyer_paid / buyer_m3, 3) if buyer_m3 else None,
        "farmer_rs_per_m3_solar": round(solar_paid / solar_buyer_m3, 3) if solar_buyer_m3 else None,
        "diesel_rs_per_m3": round(cfg.diesel_rs_per_m3, 3),
        "farmer_rs_per_irrigation": round(buyer_paid / len(buyers), 1) if buyers else None,
        "farmer_rs_per_irrigation_diesel_only": round(
            sum(p.req.gross_m3 for p in buyers) * cfg.diesel_rs_per_m3 / len(buyers), 1) if buyers else None,
        "wait_days_p50": float(np.percentile(waits, 50)) if len(waits) else None,
        "wait_days_p95": float(np.percentile(waits, 95)) if len(waits) else None,
        "tenant_share_served_by_solar": round(tenant_solar / tenant_need, 4) if tenant_need else 0.0,
        "gini_solar_share_by_household": round(gini(share), 4),
        "m3_per_acre": round((pumped_m3 + diesel_m3) / area_acres, 1),
        "m3_per_kg_cereal": round(cereal_m3 / grain_kg, 3) if grain_kg else None,
        "budget_cap_m3": round(budget_cap, 1) if budget_cap else round(ref_budget.annual_m3, 1),
        "solar_extraction_m3": round(pumped_m3, 1),
        "budget_enforced": st.budget is not None,
        "budget_bound_days": st.budget_bound_days,
        "budget_exceeded_seasons": [s for s, e in exceeded.items() if e],
        "revenue_rs": round(revenue, 0),
        "revenue_water_rs": round(water_rev, 0),
        "revenue_mill_rs": round(mill_rev, 0),
        "revenue_chaff_rs": round(chaff_rev, 0),
        "revenue_battery_rs": round(batt_rev, 0),
        "owner_own_water_value_rs": round(owner_saving, 0),
        "saur_mitra_rs_per_month": round(mitra / 12, 0),
        "platform_rs_per_year": round(platform, 0),
        "owner_fpo_income_rs": round(owner_income, 0),
        "payback_years": round(capex / owner_income, 2) if owner_income > 0 else None,
        "replans": st.replans,
        "solve_s_p50": round(float(np.median(st.solve_times)), 4) if st.solve_times else None,
        "solve_s_p95": round(float(np.percentile(st.solve_times, 95)), 4) if st.solve_times else None,
        "lost_mill_kg": round(st.lost_mill_kg, 1),
        "requests": len(done),
    }


def weekly_series(st: State) -> pd.DataFrame:
    d = pd.DataFrame(st.daily)
    d["day"] = pd.to_datetime(d["day"])
    w = d.set_index("day").resample("W")[["pv_kwh", "useful_kwh", "pump_kwh", "water_m3"]].sum()
    return w
