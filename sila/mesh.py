"""Prevent: move the network's own money so a forecast shortfall never happens.

Sila never lends and never creates new debt. It only changes *when* an invoice that already exists
between two network businesses is settled:

* Early payment - a customer with spare cash pays an open invoice early. The business at risk gets the
  cash before its crunch and gives the payer a small early-payment discount (0.6% per 30 days early).
* Grace period - a supplier with spare cash agrees to receive an open invoice later. No fee is charged
  for the delay (a fee for delay would be interest).
* Chain - when the customer who owes the business at risk is itself short of spare cash, one of *its*
  customers pays it early first, and the cash passes along the chain.

Every helper is checked against its own P10 (pessimistic) forecast: after helping it must still hold
at least PAYER_BUFFER_DAYS of its own outflows, and one move may use at most MAX_MOVE_SHARE of its
spare cash. Every proposal is re-forecast before it is shown, and nothing happens without both owners
accepting.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field

import numpy as np
import pandas as pd

from .config import (
    EARLY_PAY_RATE_30D,
    GRACE_DAYS,
    HORIZON,
    ILLUSTRATIVE_LOAN_APR,
    MAX_MOVE_SHARE,
    MIN_MOVE,
    PAYER_BUFFER_DAYS,
)
from .forecast import Forecast, Forecaster
from .ledger import Ledger

ALERT_P = 0.3          # a business is "at risk" when P(shortfall within 28 days) >= this
SAFE_P = 0.15          # a helper must have P(shortfall) below this to be asked
CUSHION = 2_000        # AED kept on top of the forecast gap


@dataclass
class Leg:
    invoice_id: str
    row: int
    payer: str
    payee: str
    amount: float
    from_day: int          # expected settlement day (relative to today) without Sila
    to_day: int            # agreed settlement day (relative to today)
    fee: float             # paid by the payee to the payer (early payment only)


@dataclass
class Advisory:
    """A shortfall the network cannot cover: warn early and point the owner to their bank."""
    business: str
    shortfall_day: int
    gap: float             # cash still missing after any moves (P10 view)
    covered: float         # cash the network moves cover
    reason: str


@dataclass
class Move:
    kind: str              # early_payment | grace | chain
    helps: str             # business protected
    helper: str            # business providing the liquidity
    legs: list[Leg]
    amount: float
    fee: float
    loan_cost: float       # what the same cover would cost as a short-term loan (illustrative)
    cover_days: int
    shortfall_day: int     # day (1..28) the business would first run short
    helper_buffer_days: float  # days of its own outflows the helper still holds after helping (P10)
    id: str = ""
    status: str = "proposed"
    verified: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        d = asdict(self)
        d["legs"] = [asdict(x) for x in self.legs]
        return d


class Mesh:
    def __init__(self, forecaster: Forecaster, alert_p: float = ALERT_P, recovery: bool = True, max_moves: int = 5):
        self.F = forecaster
        self.alert_p = alert_p
        self.recovery = recovery          # also help businesses that are already short get back to positive
        self.max_moves = max_moves

    # ---------------------------------------------------------------------------------------
    def _capacity(self, fc: Forecast) -> tuple[np.ndarray, np.ndarray]:
        """Spare cash per business and day (P10 path minus a buffer of its own outflows), and the buffer."""
        H = HORIZON
        daily_out = (fc.sched + fc.running + fc.payables).sum(axis=1) / H
        buffer = PAYER_BUFFER_DAYS * daily_out
        spare = fc.q10 - buffer[:, None]
        return spare, buffer

    def propose(self, fc: Forecast, ledger: Ledger | None = None) -> list[Move]:
        led = ledger or self.F.led
        ids = led.ids
        H = HORIZON
        spare, buffer = self._capacity(fc)
        spare = spare.copy()
        daily_out = np.maximum(buffer / max(PAYER_BUFFER_DAYS, 1), 1.0)
        at_risk = np.where((fc.p_short >= self.alert_p) & ((fc.balance >= 0) | self.recovery))[0]
        helper_ok = fc.p_short < SAFE_P
        # prevention first (still positive today, soonest crunch first), then recovery of those already short
        key = fc.first_day[at_risk] + 100 * (fc.first_day[at_risk] == 0) + 1_000 * (fc.balance[at_risk] < 0)
        at_risk = at_risk[np.argsort(key, kind="stable")]

        recv = fc.open_recv
        recv = recv[(recv.payer_i >= 0) & ~recv.agreed.fillna(False).astype(bool)]
        pay = fc.open_pay
        pay = pay[(pay.payee_i >= 0) & ~pay.agreed.fillna(False).astype(bool)]
        used_rows: set[int] = set()
        moves: list[Move] = []
        self.advisories: list[Advisory] = []

        for a in at_risk:
            need = np.maximum(0.0, -fc.q10[a] + CUSHION)          # [H] cash short on each day (pessimistic)
            if need.max() <= 0:
                continue
            first = int(fc.first_day[a]) or int(np.argmax(need > 0)) + 1
            chosen: list[Move] = []

            def gain_early(o: int, amt: float) -> np.ndarray:
                g = np.zeros(H)
                g[: max(0, min(o, H + 1) - 1)] = amt
                return g

            for _ in range(self.max_moves):
                if need.max() < MIN_MOVE / 2:
                    break
                best = None
                # 1) a network customer pays an open invoice early
                cand = recv[(recv.payee_i == a) & ~recv.index.isin(list(used_rows))]
                for row, r in cand.iterrows():
                    b = int(r.payer_i)
                    if b == a or not helper_ok[b]:
                        continue
                    o = int(np.rint(r.r50))
                    if o <= 1:
                        continue
                    hz = min(o, H + 1) - 1
                    cap = MAX_MOVE_SHARE * spare[b, :hz].min() if hz > 0 else 0.0
                    want = need[:hz].max() if hz > 0 else 0.0
                    amt = float(min(r.amount, cap, np.ceil(want / 1_000) * 1_000))
                    if amt < MIN_MOVE:
                        continue
                    covered = np.minimum(need, gain_early(o, amt)).sum()
                    if covered <= 0:
                        continue
                    fee = EARLY_PAY_RATE_30D * amt * (o - 1) / 30
                    score = covered - 50 * fee
                    if best is None or score > best[0]:
                        best = (score, "early_payment", [(row, r, b, amt, o, 1, fee)], gain_early(o, amt), b)
                # 2) a network supplier gives a grace period on what the business owes it
                cand = pay[(pay.payer_i == a) & ~pay.index.isin(list(used_rows))]
                for row, r in cand.iterrows():
                    c = int(r.payee_i)
                    if c == a or not helper_ok[c]:
                        continue
                    o = int(np.rint(r.r50))
                    if o > H or o < 1 or need[o - 1:].max() <= 0:
                        continue
                    new = min(o + GRACE_DAYS, H + 1)
                    cap = MAX_MOVE_SHARE * spare[c, o - 1:new - 1].min()
                    if cap < MIN_MOVE:
                        continue
                    amt = float(min(r.amount, cap))
                    if amt < MIN_MOVE:
                        continue
                    g = np.zeros(H)
                    g[o - 1:new - 1] = amt
                    covered = np.minimum(need, g).sum()
                    if covered <= 0:
                        continue
                    score = covered
                    if best is None or score > best[0]:
                        best = (score, "grace", [(row, r, c, amt, o, new, 0.0)], g, c)
                # 3) chain: a customer short of spare cash is paid early by its own customer first
                if best is None:
                    cand = recv[(recv.payee_i == a) & ~recv.index.isin(list(used_rows))]
                    for row, r in cand.iterrows():
                        b = int(r.payer_i)
                        o = int(np.rint(r.r50))
                        if b == a or o <= 1 or fc.p_short[b] >= ALERT_P:
                            continue
                        hz = min(o, H + 1) - 1
                        for row2, r2 in recv[(recv.payee_i == b) & ~recv.index.isin(list(used_rows))].iterrows():
                            d = int(r2.payer_i)
                            o2 = int(np.rint(r2.r50))
                            if d in (a, b) or not helper_ok[d] or o2 <= hz:
                                continue
                            cap = MAX_MOVE_SHARE * spare[d, :min(o2, H + 1) - 1].min()
                            amt = float(min(r.amount, r2.amount, cap, np.ceil(need[:hz].max() / 1_000) * 1_000))
                            if amt < MIN_MOVE:
                                continue
                            g = gain_early(o, amt)
                            covered = np.minimum(need, g).sum()
                            fee1 = EARLY_PAY_RATE_30D * amt * (o2 - 1) / 30
                            fee2 = EARLY_PAY_RATE_30D * amt * (o - 1) / 30
                            score = covered - 50 * (fee1 + fee2)
                            if covered > 0 and (best is None or score > best[0]):
                                best = (score, "chain", [(row2, r2, d, amt, o2, 1, fee1), (row, r, b, amt, o, 1, fee2)], g, d)
                if best is None:
                    break
                _, kind, legs_raw, gain, helper = best
                legs = []
                for row, r, who, amt, o, new, fee in legs_raw:
                    used_rows.add(row)
                    legs.append(Leg(invoice_id=str(r.invoice_id), row=int(row), payer=ids[int(r.payer_i)],
                                    payee=ids[int(r.payee_i)], amount=round(amt, 2), from_day=int(o), to_day=int(new),
                                    fee=round(fee, 2)))
                    # consume the helper's spare cash on the days it is out of pocket
                    lo, hi = (0, min(o, H + 1) - 1) if new < o else (o - 1, new - 1)
                    spare[who, lo:hi] -= amt
                amt = legs[-1].amount
                l0 = legs[0]
                loss = np.zeros(H)   # helper's cash given up, by day
                if l0.to_day < l0.from_day:
                    loss[: min(l0.from_day, H + 1) - 1] = l0.amount
                else:
                    loss[l0.from_day - 1:l0.to_day - 1] = l0.amount
                need = np.maximum(0.0, need - gain)
                cover_days = int((gain > 0).sum())
                fee = sum(x.fee for x in legs if x.payee == ids[a]) if kind != "grace" else 0.0
                chosen.append(Move(
                    kind=kind, helps=ids[a], helper=ids[helper], legs=legs, amount=amt, fee=round(fee, 2),
                    loan_cost=round(ILLUSTRATIVE_LOAN_APR * amt * abs(legs[-1].from_day - legs[-1].to_day) / 365, 2),
                    cover_days=cover_days,
                    shortfall_day=first,
                    helper_buffer_days=round(float((fc.q10[helper] - loss).min() / daily_out[helper]), 1),
                ))
            moves += chosen
            if need.max() >= MIN_MOVE and fc.balance[a] >= 0:
                n_links = int(((recv.payee_i == a) | False).sum() + (pay.payer_i == a).sum())
                reason = ("no open invoices with network partners" if n_links == 0 else
                          "network partners do not have enough spare cash" if not chosen else
                          "the gap is larger than the network can safely cover")
                self.advisories.append(Advisory(business=ids[a], shortfall_day=first, gap=round(float(need.max()), -2),
                                                covered=round(sum(m.amount for m in chosen), -2), reason=reason))
        moves = self._merge(moves)
        for i, m in enumerate(moves):
            m.id = f"M{fc.t:04d}-{i + 1:02d}"
        return moves

    @staticmethod
    def _merge(moves: list[Move]) -> list[Move]:
        """One suggestion per (business, helper, kind): several invoices between the same two firms become one move."""
        out: dict[tuple, Move] = {}
        for m in moves:
            key = (m.helps, m.helper, m.kind) if m.kind != "chain" else (m.helps, m.helper, m.kind, id(m))
            if key not in out:
                out[key] = m
                continue
            a = out[key]
            a.legs += m.legs
            a.amount = round(a.amount + m.amount, 2)
            a.fee = round(a.fee + m.fee, 2)
            a.loan_cost = round(a.loan_cost + m.loan_cost, 2)
            a.cover_days = max(a.cover_days, m.cover_days)
            a.helper_buffer_days = min(a.helper_buffer_days, m.helper_buffer_days)
        return list(out.values())

    # ---------------------------------------------------------------------------------------
    @staticmethod
    def apply(ledger: Ledger, moves: list[Move], t: int) -> Ledger:
        """Apply accepted moves to a ledger (settlement days are relative to day t)."""
        for m in moves:
            for leg in m.legs:
                ledger.resettle(leg.row, t + leg.to_day, amount=leg.amount)
                if leg.fee:
                    pi, ei = ledger.idx[leg.payer], ledger.idx[leg.payee]
                    ledger.adjust(ei, t + leg.to_day, -leg.fee)
                    ledger.adjust(pi, t + leg.to_day, +leg.fee)
        return ledger

    def verify(self, t: int, ledger: Ledger, moves: list[Move], before: Forecast) -> tuple[list[Move], Forecast]:
        """Re-forecast with the moves in place; drop any move whose helper would become at risk."""
        for _ in range(3):
            trial = self.apply(ledger.copy(), moves, t)
            after = self.F.forecast(t, ledger=trial)
            bad = set()
            for m in moves:
                for leg in m.legs:
                    for who in (leg.payer, leg.payee):
                        i = trial.idx[who]
                        if who != m.helps and after.p_short[i] > max(before.p_short[i] + 0.05, SAFE_P):
                            bad.add(m.id)
            if not bad:
                break
            moves = [m for m in moves if m.id not in bad]
        for m in moves:
            i = trial.idx[m.helps]
            h = trial.idx[m.helper]
            m.verified = dict(p_short_before=round(float(before.p_short[i]), 3), p_short_after=round(float(after.p_short[i]), 3),
                              gap_before=round(float(before.gap80[i]), -2), gap_after=round(float(after.gap80[i]), -2),
                              helper_p_before=round(float(before.p_short[h]), 3), helper_p_after=round(float(after.p_short[h]), 3))
        return moves, after


def moves_frame(moves: list[Move]) -> pd.DataFrame:
    return pd.DataFrame([{k: v for k, v in m.to_dict().items() if k != "legs"} for m in moves])
