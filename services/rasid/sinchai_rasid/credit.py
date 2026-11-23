"""Harvest-linked repayment: "book now, pay a share after harvest".

A tenant often has no cash in the weeks before harvest, which is exactly when wheat needs its last watering.
The offer splits a booking into a part paid now (so the Saur Mitra still collects cash) and a part due a week
after the plot's expected harvest. The fee is priced at the published Kisan Credit Card rate, so deferring
is never dearer than a crop loan. The limit starts small and grows only with on-time repayment recorded in
the ledger; anyone with an overdue after-harvest balance is not offered more.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import date, timedelta

from sinchai_planner.fao56 import CROPS
from sinchai_schemas import constants as C

GRACE_DAYS = 7


@dataclass
class Repayment:
    due: date
    amount_rs: float
    paid_on: date | None = None

    def on_time(self) -> bool:
        return self.paid_on is not None and self.paid_on <= self.due

    def overdue(self, today: date) -> bool:
        return self.paid_on is None and today > self.due


@dataclass
class HarvestOffer:
    eligible: bool
    reason_en: str
    reason_hi: str
    price_rs: float
    pay_now_rs: float
    after_harvest_rs: float
    fee_rs: float
    due: str | None
    limit_rs: float
    outstanding_rs: float

    def to_dict(self) -> dict:
        return asdict(self)


def harvest_date(crop_key: str, today: date) -> date:
    """Expected harvest of the crop now in the field: the latest sowing on or before today plus season length."""
    c = CROPS[crop_key]
    for y in (today.year, today.year - 1):
        sow = date(y, c.sow_month, c.sow_day)
        if sow <= today:
            h = sow + timedelta(days=c.length)
            if h >= today:
                return h
            break
    # The crop's season is over: the next harvest.
    sow = date(today.year if date(today.year, c.sow_month, c.sow_day) > today else today.year + 1, c.sow_month, c.sow_day)
    return sow + timedelta(days=c.length)


def limit_rs(history: list[Repayment]) -> float:
    base = C.get("harvest_credit_limit_rs")
    clean = sum(1 for r in history if r.on_time())
    return base * (1 + 0.5 * min(clean, 4))  # up to 3x after four on-time repayments


def offer(price_rs: float, crop_key: str, today: date, history: list[Repayment]) -> HarvestOffer:
    outstanding = sum(r.amount_rs for r in history if r.paid_on is None)
    lim = limit_rs(history)
    if any(r.overdue(today) for r in history):
        return HarvestOffer(False, "An earlier after-harvest payment is overdue", "पिछला फ़सल-बाद भुगतान बाकी है",
                            price_rs, price_rs, 0.0, 0.0, None, lim, outstanding)
    room = max(lim - outstanding, 0.0)
    later = round(min(price_rs * C.get("harvest_credit_share_cap"), room), 0)
    if later < 10:
        return HarvestOffer(False, "After-harvest limit is used up", "फ़सल-बाद की सीमा पूरी हो गई", price_rs,
                            price_rs, 0.0, 0.0, None, lim, outstanding)
    due = harvest_date(crop_key, today) + timedelta(days=GRACE_DAYS)
    days = (due - today).days
    fee = round(later * C.get("harvest_credit_fee_rate") * days / 365, 0)
    return HarvestOffer(True, f"Pay Rs {price_rs - later:.0f} now, Rs {later + fee:.0f} by {due:%d %b}",
                        f"अभी ₹{price_rs - later:.0f}, फ़सल के बाद {due:%d/%m} तक ₹{later + fee:.0f}",
                        price_rs, round(price_rs - later, 0), later, fee, due.isoformat(), lim, outstanding)
