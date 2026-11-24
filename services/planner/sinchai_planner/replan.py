"""Rolling re-planner and plain-language plan diffs.

Re-plan rule: every 30 minutes, or immediately when the P50 forecast for the
remaining day moves by more than `shift_threshold`; slots starting within `freeze_min` minutes are
frozen so nobody's water is moved at the last moment.
"""

from __future__ import annotations

from dataclasses import dataclass, replace

import numpy as np

from .optimizer import Plan, PlanInput, Scenario, solve


@dataclass
class Change:
    kind: str  # "moved" | "added" | "dropped" | "load_moved"
    subject: str  # request id or load name
    household: str | None
    old_slots: list[str]
    new_slots: list[str]
    reason_en: str
    reason_hi: str


def forecast_shift(old: list[Scenario], new: list[Scenario], from_slot: int) -> float:
    """Relative change in remaining-day P50 energy."""
    o = next(s for s in old if s.name == "P50").pv_kw[from_slot:]
    n = next(s for s in new if s.name == "P50").pv_kw[from_slot:]
    base = float(np.sum(o))
    return abs(float(np.sum(n)) - base) / base if base > 0 else 0.0


def should_replan(old: list[Scenario], new: list[Scenario], from_slot: int, minutes_since: float,
                  shift_threshold: float = 0.15, period_min: float = 30) -> bool:
    return minutes_since >= period_min or forecast_shift(old, new, from_slot) > shift_threshold


def replan(inp: PlanInput, prev: Plan, now_slot: int, new_scenarios: list[Scenario],
           freeze_min: float = 60, delivered_m3: dict[str, float] | None = None) -> Plan:
    """Re-solve from `now_slot` with the new forecast, freezing past and near-term slots."""
    freeze_slots = int(np.ceil(freeze_min / (inp.slot_h * 60)))
    frozen = {t: a for t, a in prev.assignment().items() if t < now_slot + freeze_slots}
    reqs = inp.requests
    if delivered_m3:
        reqs = [replace(r, remaining_m3=max(r.remaining_m3 - delivered_m3.get(r.id, 0.0), 0.0)) for r in reqs]
    # Past slots stay frozen but deliver nothing further in the re-solve.
    scen = []
    for s in new_scenarios:
        pv = np.array(s.pv_kw, dtype=float).copy()
        pv[:now_slot] = 0.0
        scen.append(Scenario(s.name, s.prob, pv))
    frozen_future = {t: a for t, a in frozen.items() if t >= now_slot}
    frozen_past = {t: "idle" for t in range(now_slot)}
    new_inp = replace(inp, requests=reqs, scenarios=scen, frozen={**frozen_past, **frozen_future})
    plan = solve(new_inp)
    # Restore the historical actions for display.
    for sp in plan.slots:
        if sp.slot < now_slot:
            old = prev.slots[sp.slot]
            sp.action, sp.household = old.action, old.household
    return plan


def _slots_of(plan: Plan, action: str) -> list[str]:
    return [s.start[11:16] for s in plan.slots if s.action == action]


def ranges(labels: list[str]) -> str:
    """['10:00','10:30','11:00','14:00'] -> '10:00-11:30, 14:00-14:30' (step inferred, default 60 min)."""
    if not labels:
        return "-"
    mins = [int(x[:2]) * 60 + int(x[3:5]) for x in labels]
    step = min((b - a for a, b in zip(mins, mins[1:], strict=False) if b > a), default=60)
    out, start, prev = [], mins[0], mins[0]
    for m in mins[1:] + [None]:
        if m is not None and m == prev + step:
            prev = m
            continue
        end = prev + step
        out.append(f"{start // 60:02d}:{start % 60:02d}-{end // 60:02d}:{end % 60:02d}")
        if m is not None:
            start = prev = m
    return ", ".join(out)


def explain_diff(old: Plan, new: Plan, old_scen: list[Scenario], new_scen: list[Scenario]) -> list[Change]:
    """Compare two plans and attach a reason drawn from the forecast change."""
    o50 = next(s for s in old_scen if s.name == "P50").pv_kw
    n50 = next(s for s in new_scen if s.name == "P50").pv_kw
    drops = [old.slots[t].start[11:16] for t in range(len(o50)) if n50[t] < 0.85 * o50[t] and o50[t] > 0.3]
    rises = [old.slots[t].start[11:16] for t in range(len(o50)) if n50[t] > 1.15 * o50[t] + 0.2]
    if drops:
        cause_en = f"less sun now expected {ranges(drops)}"
        cause_hi = f"{ranges(drops)} बजे बादल / कम धूप का अनुमान"
    elif rises:
        cause_en = f"more sun now expected {ranges(rises)}"
        cause_hi = f"{ranges(rises)} बजे ज़्यादा धूप का अनुमान"
    else:
        cause_en, cause_hi = "updated bookings and delivered water", "बुकिंग और दिए गए पानी में बदलाव"

    actions = {a for a in old.assignment().values()} | {a for a in new.assignment().values()}
    hh_of = {s.action: s.household for p in (old, new) for s in p.slots if s.household}
    changes: list[Change] = []
    for a in sorted(actions - {"idle"}):
        os_, ns_ = _slots_of(old, a), _slots_of(new, a)
        if os_ == ns_:
            continue
        if a.startswith("req:"):
            kind = "moved" if os_ and ns_ else ("added" if ns_ else "dropped")
            subj = a[4:]
            if kind == "moved":
                en = f"{cause_en}: water moved from {ranges(os_)} to {ranges(ns_)}"
                hi = f"{cause_hi}: पानी का समय {ranges(os_)} से {ranges(ns_)} किया गया"
            elif kind == "added":
                en = f"{cause_en}: water added {ranges(ns_)}"
                hi = f"{cause_hi}: {ranges(ns_)} बजे पानी का समय जोड़ा गया"
            else:
                en = f"{cause_en}: {ranges(os_)} released, booking carried to the next sunny window"
                hi = f"{cause_hi}: {ranges(os_)} का समय अगली धूप वाली खिड़की में जाएगा"
            changes.append(Change(kind, subj, hh_of.get(a), os_, ns_, en, hi))
        else:
            name_hi = {"mill": "चक्की", "chaff": "कुट्टी मशीन"}.get(a, a)
            if not ns_:
                en = f"{cause_en}: {a} at {ranges(os_)} cancelled for today; the sun goes to water first"
                hi = f"{cause_hi}: {name_hi} का {ranges(os_)} का समय आज रद्द; धूप पहले पानी को"
            elif not os_:
                en = f"{cause_en}: {a} added {ranges(ns_)}"
                hi = f"{cause_hi}: {name_hi} {ranges(ns_)} जोड़ा गया"
            else:
                en = f"{cause_en}: {a} moved from {ranges(os_)} to {ranges(ns_)}"
                hi = f"{cause_hi}: {name_hi} {ranges(os_)} से {ranges(ns_)} पर"
            changes.append(Change("load_moved", a, None, os_, ns_, en, hi))
    ob, nb = old.total("battery"), new.total("battery")
    if abs(nb - ob) > 0.2:
        changes.append(Change("load_moved", "battery", None, [], [],
                              f"{cause_en}: battery charging {ob:.1f} -> {nb:.1f} kWh",
                              f"{cause_hi}: बैटरी चार्जिंग {ob:.1f} से {nb:.1f} kWh"))
    return changes
