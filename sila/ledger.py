"""Daily cash balances for every business, with invoice settlement dates that can be changed.

The non-invoice flows (sales, payroll, rent cheques, VAT, utilities, running costs) are fixed.
Invoice payments move cash from the payer to the payee on the settlement day. Sila only ever
changes *when* an existing invoice is settled - it never creates new money or new debt - so
a counterfactual is just the same ledger with some settlement dates moved.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date

import numpy as np
import pandas as pd

from .config import START
from .synth import World


def day_index(d) -> int:
    return (pd.Timestamp(d).date() - START).days


@dataclass
class Ledger:
    world: World
    ids: list[str]
    idx: dict[str, int]
    base: np.ndarray                 # [n_sme, n_days] fixed daily net flows
    opening: np.ndarray              # [n_sme]
    inv: pd.DataFrame                # invoices with integer day columns + mutable settlement day
    inv_flow: np.ndarray = field(default=None)   # [n_sme, n_days] invoice cash flows
    balance: np.ndarray = field(default=None)    # [n_sme, n_days] end-of-day balance
    extra: np.ndarray = field(default=None)      # [n_sme, n_days] small adjustments (early-payment discounts)

    @classmethod
    def build(cls, world: World) -> Ledger:
        ids = [s["id"] for s in world.smes]
        idx = {k: i for i, k in enumerate(ids)}
        nd = len(world.days)
        base = np.zeros((len(ids), nd))
        f = world.flows
        np.add.at(base, (f.sme.map(idx).values, f.t.values), f.amount.values)
        inv = world.invoices.copy()
        inv["t_issue"] = (inv.issue - pd.Timestamp(START)).dt.days
        inv["t_due"] = (inv.due - pd.Timestamp(START)).dt.days
        inv["t_paid"] = (inv.paid - pd.Timestamp(START)).dt.days      # actual (historical) settlement
        inv["t_settle"] = inv["t_paid"].astype(int)                     # settlement in this ledger (mutable)
        inv["payee_i"] = inv.payee.map(idx).fillna(-1).astype(int)
        inv["payer_i"] = inv.payer.map(idx).fillna(-1).astype(int)
        inv["agreed"] = False      # True once a settlement date has been agreed through Sila
        opening = np.array([s["opening_cash"] for s in world.smes], dtype=float)
        led = cls(world=world, ids=ids, idx=idx, base=base, opening=opening, inv=inv.reset_index(drop=True))
        led.recompute()
        return led

    @property
    def n_days(self) -> int:
        return self.base.shape[1]

    def recompute(self) -> None:
        nd = self.n_days
        flow = np.zeros_like(self.base)
        inv = self.inv[(self.inv.t_settle >= 0) & (self.inv.t_settle < nd)]
        m = inv.payee_i >= 0
        np.add.at(flow, (inv.payee_i[m].values, inv.t_settle[m].values), inv.amount[m].values)
        m = inv.payer_i >= 0
        np.add.at(flow, (inv.payer_i[m].values, inv.t_settle[m].values), -inv.amount[m].values)
        self.inv_flow = flow
        if self.extra is None:
            self.extra = np.zeros_like(self.base)
        self.balance = self.opening[:, None] + np.cumsum(self.base + flow + self.extra, axis=1)

    def copy(self) -> Ledger:
        c = Ledger(world=self.world, ids=self.ids, idx=self.idx, base=self.base, opening=self.opening,
                   inv=self.inv.copy())
        c.inv_flow = self.inv_flow.copy()
        c.extra = self.extra.copy()
        c.balance = self.balance.copy()
        return c

    # --- the only two things Sila can do: settle an invoice earlier, or later ---------------
    def resettle(self, row: int, new_t: int, amount: float | None = None) -> int | None:
        """Move settlement of invoice `row` to day `new_t`. If `amount` is less than the open amount,
        the invoice is split and only that part moves. Returns the index of the moved row."""
        r = self.inv.loc[row]
        amt = float(r.amount)
        if amount is not None and amount < amt - 0.5:
            part = r.copy()
            part["amount"] = round(amount, 2)
            part["invoice_id"] = f"{r.invoice_id}-P{int(new_t)}"
            self.inv.at[row, "amount"] = amt - part["amount"]
            self._shift(r.payee_i, r.payer_i, int(r.t_settle), int(new_t), part["amount"])
            part["t_settle"] = int(new_t)
            part["agreed"] = True
            self.inv.loc[len(self.inv)] = part
            return len(self.inv) - 1
        self._shift(r.payee_i, r.payer_i, int(r.t_settle), int(new_t), amt)
        self.inv.at[row, "t_settle"] = int(new_t)
        self.inv.at[row, "agreed"] = True
        return row

    def adjust(self, who: int, t: int, amount: float) -> None:
        """A one-off cash adjustment (e.g. an early-payment discount) for business `who` on day `t`."""
        if who < 0 or not 0 <= t < self.n_days:
            return
        self.extra[who, t] += amount
        self.balance[who, t:] += amount

    def _shift(self, payee: int, payer: int, old_t: int, new_t: int, amt: float) -> None:
        nd = self.n_days
        for who, sign in ((payee, 1.0), (payer, -1.0)):
            if who < 0:
                continue
            if 0 <= old_t < nd:
                self.inv_flow[who, old_t] -= sign * amt
            if 0 <= new_t < nd:
                self.inv_flow[who, new_t] += sign * amt
            lo = max(0, min(old_t, new_t))
            self.balance[who, lo:] = (self.balance[who, lo - 1] if lo > 0 else self.opening[who]) + \
                np.cumsum(self.base[who, lo:] + self.inv_flow[who, lo:] + self.extra[who, lo:])

    # --- views --------------------------------------------------------------------------------
    def open_invoices(self, t: int) -> pd.DataFrame:
        """Invoices issued on or before day t and not yet settled at the end of day t."""
        inv = self.inv
        return inv[(inv.t_issue <= t) & (inv.t_settle > t)]


def shortfall_days(balance: np.ndarray, t0: int, t1: int) -> np.ndarray:
    """Number of days with a negative balance per business in [t0, t1)."""
    return (balance[:, t0:t1] < 0).sum(axis=1)


def shortfall_episodes(balance: np.ndarray, t0: int, t1: int, gap: int = 3) -> list[tuple[int, int, float]]:
    """(business, first negative day, depth) for each episode starting in [t0, t1).
    A new episode needs at least `gap` non-negative days before it."""
    out = []
    neg = balance < 0
    for i in range(balance.shape[0]):
        last_neg = -10_000
        t = max(0, t0 - gap)
        while t < t1:
            if neg[i, t]:
                if t >= t0 and t - last_neg > gap:
                    end = t
                    while end < balance.shape[1] and neg[i, end]:
                        end += 1
                    out.append((i, t, float(balance[i, t:end].min())))
                last_neg = t
            t += 1
    return out


def to_date(t: int) -> date:
    return (pd.Timestamp(START) + pd.Timedelta(days=int(t))).date()
