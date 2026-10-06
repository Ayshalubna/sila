"""Predict: probabilistic 28-day cash forecast for every business.

Three pieces, all trained only on data up to TRAIN_END:

1. Payment-timing model (LightGBM quantile regression): for every open invoice, how many more
   days until it is actually paid (P10 / P50 / P90), from the payer's track record and the invoice.
2. Sales model (LightGBM quantile regression): daily walk-in / card sales for the next 28 days,
   relative to the business's recent level, with weekday, Ramadan, Eid and summer effects.
3. Known obligations: WPS payroll, post-dated rent cheques, VAT, utilities, owner drawings and
   supplier invoices - detected from the categorised bank history.

A Monte-Carlo simulation combines them into balance paths, giving each business a probability of
running short, when, and by how much.
"""
from __future__ import annotations

import pickle
import warnings
from dataclasses import dataclass
from datetime import timedelta

import lightgbm as lgb
import numpy as np
import pandas as pd

from .config import ARTIFACTS, EID, HORIZON, N_PATHS, RAMADAN, START, TRAIN_END
from .ledger import Ledger, day_index
from .synth import SECTORS

QS = (0.1, 0.5, 0.9)
Z90 = 1.2816
SECTOR_CODE = {k: i for i, k in enumerate(SECTORS)}
RECURRING = ("payroll", "utilities", "owner_drawings")


def _calendar(n_days: int, pad: int = HORIZON + 5):
    days = pd.date_range(START, periods=n_days + pad, freq="D")
    ram = np.zeros(len(days), dtype=np.int8)
    for a, b in RAMADAN:
        ram[(days >= pd.Timestamp(a)) & (days <= pd.Timestamp(b))] = 1
    eid = np.zeros(len(days), dtype=np.int8)
    for e in EID:
        eid[(days >= pd.Timestamp(e)) & (days <= pd.Timestamp(e) + pd.Timedelta(days=3))] = 1
    return dict(dow=days.dayofweek.values, month=days.month.values, dom=days.day.values, ram=ram, eid=eid,
                summer=np.isin(days.month.values, [7, 8]).astype(np.int8))


# ---------------------------------------------------------------------------------------------
# payment timing
# ---------------------------------------------------------------------------------------------
DELAY_FEATURES = ["hist_n", "hist_mean", "hist_std", "hist_p90", "hist_late30", "hist_last", "hist_recent",
                  "log_amount", "rel_amount", "terms", "age", "to_due", "overdue", "due_month",
                  "due_ram", "due_summer", "payer_external"]
DELAY_LABELS = {
    "hist_mean": "Payer's usual delay", "hist_p90": "Payer's worst delays", "hist_late30": "Share paid >30 days late",
    "hist_last": "Payer's most recent delay", "hist_recent": "Payer's recent delays", "to_due": "Days until due",
    "overdue": "Already overdue", "age": "Invoice age", "terms": "Payment terms", "log_amount": "Invoice size",
    "rel_amount": "Size vs payer's usual", "due_ram": "Due in Ramadan", "due_summer": "Due in summer",
    "hist_n": "Payer history length", "hist_std": "Payer's consistency", "due_month": "Due month",
    "payer_external": "Outside the network",
}


class PayerHistory:
    """As-of statistics of each payer's past lateness, using only invoices settled before the origin."""

    def __init__(self, inv: pd.DataFrame):
        h = inv[["payer", "t_paid", "t_due", "amount"]].copy()
        h["late"] = (h.t_paid - h.t_due).astype(float)
        self.by_payer = {}
        for p, g in h.sort_values("t_paid").groupby("payer"):
            late = g.late.values
            self.by_payer[p] = (g.t_paid.values, late, np.cumsum(late), np.cumsum(late ** 2),
                                np.cumsum(late > 30), g.amount.values, np.cumsum(g.amount.values))

    def stats(self, payer: np.ndarray, t: np.ndarray) -> np.ndarray:
        out = np.full((len(payer), 8), np.nan)
        order = pd.Series(np.arange(len(payer))).groupby(payer).indices
        for p, rows in order.items():
            rec = self.by_payer.get(p)
            if rec is None:
                continue
            tp, late, cs, cs2, c30, amt, camt = rec
            k = np.searchsorted(tp, t[rows], side="left")   # settled strictly before origin
            ok = k > 0
            r, kk = rows[ok], k[ok]
            n = kk.astype(float)
            mean = cs[kk - 1] / n
            out[r, 0] = n
            out[r, 1] = mean
            out[r, 2] = np.sqrt(np.maximum(cs2[kk - 1] / n - mean ** 2, 0))
            out[r, 4] = c30[kk - 1] / n
            out[r, 5] = late[kk - 1]
            lo = np.maximum(kk - 8, 0)
            out[r, 6] = (cs[kk - 1] - np.where(lo > 0, cs[lo - 1], 0)) / (kk - lo)
            out[r, 7] = camt[kk - 1] / n
            # rough p90 from mean/std (cheap and monotone)
            out[r, 3] = out[r, 1] + 1.28 * out[r, 2]
        return out


def delay_features(inv: pd.DataFrame, t: np.ndarray, hist: PayerHistory, cal: dict) -> pd.DataFrame:
    st = hist.stats(inv.payer.values, t)
    due = inv.t_due.values.astype(int)
    dclip = np.clip(due, 0, len(cal["month"]) - 1)
    f = pd.DataFrame({
        "hist_n": st[:, 0], "hist_mean": st[:, 1], "hist_std": st[:, 2], "hist_p90": st[:, 3],
        "hist_late30": st[:, 4], "hist_last": st[:, 5], "hist_recent": st[:, 6],
        "log_amount": np.log1p(inv.amount.values), "rel_amount": inv.amount.values / np.where(np.isnan(st[:, 7]), inv.amount.values, st[:, 7]),
        "terms": inv.terms.values, "age": t - inv.t_issue.values, "to_due": due - t,
        "overdue": (t > due).astype(int), "due_month": cal["month"][dclip],
        "due_ram": cal["ram"][dclip], "due_summer": cal["summer"][dclip],
        "payer_external": inv.payer.str.startswith("X").astype(int).values,
    })
    return f


# ---------------------------------------------------------------------------------------------
# sales
# ---------------------------------------------------------------------------------------------
SALES_FEATURES = ["h", "dow", "month", "ram", "eid", "summer", "sector", "r_dow", "r_7", "r_91", "log_level"]


class SalesHistory:
    def __init__(self, sales: np.ndarray):
        self.S = sales
        self.cs = np.concatenate([np.zeros((sales.shape[0], 1)), np.cumsum(sales, axis=1)], axis=1)

    def mean(self, t: int, w: int) -> np.ndarray:
        lo = max(0, t + 1 - w)
        return (self.cs[:, t + 1] - self.cs[:, lo]) / max(1, t + 1 - lo)

    def dow_mean(self, t: int, weeks: int = 8) -> np.ndarray:
        """[n, 7] mean sales by weekday over the last `weeks` weeks."""
        lo = max(0, t + 1 - 7 * weeks)
        block = self.S[:, lo:t + 1]
        dows = (np.arange(lo, t + 1) + START.weekday()) % 7
        out = np.zeros((self.S.shape[0], 7))
        for d in range(7):
            m = dows == d
            if m.any():
                out[:, d] = block[:, m].mean(axis=1)
        return out


def sales_features(sh: SalesHistory, t: int, rows: np.ndarray, sector: np.ndarray, cal: dict) -> tuple[pd.DataFrame, np.ndarray]:
    level = np.maximum(sh.mean(t, 28)[rows], 1.0)
    dm = sh.dow_mean(t)[rows]
    m7, m91 = sh.mean(t, 7)[rows], sh.mean(t, 91)[rows]
    H = HORIZON
    tt = t + np.arange(1, H + 1)
    n = len(rows)
    dow = np.tile(cal["dow"][tt], n)
    f = pd.DataFrame({
        "h": np.tile(np.arange(1, H + 1), n), "dow": dow, "month": np.tile(cal["month"][tt], n),
        "ram": np.tile(cal["ram"][tt], n), "eid": np.tile(cal["eid"][tt], n), "summer": np.tile(cal["summer"][tt], n),
        "sector": np.repeat(sector, H), "r_dow": dm[np.repeat(np.arange(n), H), dow] / np.repeat(level, H),
        "r_7": np.repeat(m7 / level, H), "r_91": np.repeat(m91 / level, H), "log_level": np.repeat(np.log(level), H),
    })
    return f, level


# ---------------------------------------------------------------------------------------------
# the forecaster
# ---------------------------------------------------------------------------------------------
@dataclass
class Forecast:
    t: int
    p_short: np.ndarray        # [n] probability the balance goes below zero within the horizon
    first_day: np.ndarray      # [n] median first negative day (1..H), 0 if none
    gap80: np.ndarray          # [n] cash needed to stay >= 0 in 80% of paths
    q10: np.ndarray            # [n, H] balance percentiles
    q50: np.ndarray
    q90: np.ndarray
    balance: np.ndarray        # [n] balance at t
    sched: np.ndarray          # [n, H] known outflows (positive numbers)
    sales50: np.ndarray        # [n, H]
    running: np.ndarray        # [n, H]
    payables: np.ndarray       # [n, H]
    recv50: np.ndarray         # [n, H] expected receipts (median timing)
    open_recv: pd.DataFrame    # receivables with predicted timing
    open_pay: pd.DataFrame     # payables with predicted timing
    sched_items: list          # [(sme_i, h, kind, amount)]


class Forecaster:
    def __init__(self, ledger: Ledger):
        self.led = ledger
        w = ledger.world
        n, nd = ledger.base.shape
        self.cal = _calendar(nd)
        f = w.flows
        idx = ledger.idx
        self.kind_mats = {}
        for k in ("sales", "running_costs"):
            m = np.zeros((n, nd))
            g = f[f.kind == k]
            np.add.at(m, (g.sme.map(idx).values, g.t.values), g.amount.values)
            self.kind_mats[k] = m
        self.sales = SalesHistory(self.kind_mats["sales"])
        self.sales_rows = np.where(self.kind_mats["sales"][:, : day_index(TRAIN_END)].sum(axis=1) > 0)[0]
        self.sector = np.array([SECTOR_CODE[s["sector"]] for s in w.smes])
        self.recurring = {k: f[f.kind == k].sort_values("t") for k in RECURRING}
        self.rent = w.rent.assign(t=(w.rent.date - pd.Timestamp(START)).dt.days, i=w.rent.sme.map(idx))
        self.hist = PayerHistory(ledger.inv[ledger.inv.t_paid < nd])
        self.delay_models: dict[float, lgb.Booster] = {}
        self.sales_models: dict[float, lgb.Booster] = {}
        self.run_mean = None
        self.spread = None   # [H] calibration factors (1.0 = raw Monte Carlo spread)

    # ---------------- training ----------------
    def train(self, verbose: bool = False) -> dict:
        te = day_index(TRAIN_END)
        inv = self.led.inv
        # origins drawn uniformly over each invoice's open life (that is how the model is used), 6 per invoice
        base = inv[(inv.t_issue >= 0) & (inv.t_paid <= te)]
        rng = np.random.default_rng(0)
        rows, ts = [], []
        for _ in range(6):
            u = rng.random(len(base))
            t = (base.t_issue.values + np.floor(u * (base.t_paid.values - base.t_issue.values))).astype(int)
            ok = t >= 30
            rows.append(base[ok])
            ts.append(t[ok])
        dtrain = pd.concat(rows)
        t_all = np.concatenate(ts)
        y = (dtrain.t_paid.values - t_all).astype(float)
        X = delay_features(dtrain, t_all, self.hist, self.cal)
        # learn the correction on top of "due date + payer's average delay"
        yr = y - self.baseline_delay(dtrain, t_all)
        params = dict(learning_rate=0.05, num_leaves=31, min_data_in_leaf=40, feature_fraction=0.9, verbose=-1, seed=1)
        for q in QS:
            self.delay_models[q] = lgb.train({**params, "objective": "quantile", "alpha": q}, lgb.Dataset(X, yr), 300)

        # sales: many origins x 28 horizons
        Xs, Ys = [], []
        for t in range(63, te - HORIZON, 7):
            f, level = sales_features(self.sales, t, self.sales_rows, self.sector[self.sales_rows], self.cal)
            tt = t + np.arange(1, HORIZON + 1)
            yv = self.kind_mats["sales"][self.sales_rows][:, tt].ravel() / np.repeat(level, HORIZON)
            Xs.append(f)
            Ys.append(yv)
        Xs = pd.concat(Xs, ignore_index=True)
        Ys = np.concatenate(Ys)
        for q in QS:
            self.sales_models[q] = lgb.train({**params, "objective": "quantile", "alpha": q, "num_leaves": 63},
                                             lgb.Dataset(Xs, Ys, categorical_feature=["sector"]), 300)
        return {"delay_rows": len(X), "sales_rows": len(Xs)}

    def calibrate(self, t0: int, t1: int, step: int = 7, target: float = 0.8) -> np.ndarray:
        """Split-conformal calibration of the P10-P90 band, per horizon day, on origins in [t0, t1).
        Uses actual balances only up to t1 + HORIZON, which must be <= the training cut-off."""
        self.spread = None
        need = []
        for t in range(t0, t1, step):
            fc = self.forecast(t)
            act = self.led.balance[:, t + 1:t + HORIZON + 1]
            lo, hi = fc.q50 - fc.q10, fc.q90 - fc.q50
            k = np.where(act < fc.q50, (fc.q50 - act) / np.maximum(lo, 1.0), (act - fc.q50) / np.maximum(hi, 1.0))
            need.append(k)
        k = np.quantile(np.concatenate(need), target, axis=0)
        k = np.maximum.accumulate(np.maximum(k, 1.0))          # never narrower, never shrinking with horizon
        self.spread = k
        return k

    def save(self, path=None):
        path = path or ARTIFACTS / "models.pkl"
        with open(path, "wb") as fh:
            pickle.dump({"delay": {q: m.model_to_string() for q, m in self.delay_models.items()},
                         "sales": {q: m.model_to_string() for q, m in self.sales_models.items()},
                         "spread": None if self.spread is None else self.spread.tolist()}, fh)

    def load(self, path=None) -> Forecaster:
        path = path or ARTIFACTS / "models.pkl"
        with open(path, "rb") as fh:
            d = pickle.load(fh)
        self.delay_models = {q: lgb.Booster(model_str=s) for q, s in d["delay"].items()}
        self.sales_models = {q: lgb.Booster(model_str=s) for q, s in d["sales"].items()}
        sp = d.get("spread")
        self.spread = None if sp is None else np.array(sp)
        return self

    # ---------------- prediction pieces ----------------
    def baseline_delay(self, inv: pd.DataFrame, t: np.ndarray) -> np.ndarray:
        """Remaining days if the payer pays as late as it usually does: due date + its average delay."""
        st = self.hist.stats(inv.payer.values, t)
        mean = np.where(np.isnan(st[:, 1]), 10.0, st[:, 1])
        return np.maximum(inv.t_due.values + mean - t, 1.0)

    def predict_delay(self, inv: pd.DataFrame, t: int) -> np.ndarray:
        """[m, 3] remaining days until payment (P10, P50, P90), at least 1."""
        if len(inv) == 0:
            return np.zeros((0, 3))
        tt = np.full(len(inv), t)
        X = delay_features(inv, tt, self.hist, self.cal)
        base = self.baseline_delay(inv, tt)
        p = np.column_stack([base + self.delay_models[q].predict(X) for q in QS])
        p = np.maximum.accumulate(np.maximum(p, 1.0), axis=1)
        return p

    def predict_sales(self, t: int) -> np.ndarray:
        """[n, H, 3] daily sales quantiles."""
        n = self.led.base.shape[0]
        out = np.zeros((n, HORIZON, 3))
        rows = self.sales_rows
        f, level = sales_features(self.sales, t, rows, self.sector[rows], self.cal)
        p = np.column_stack([self.sales_models[q].predict(f) for q in QS])
        p = np.maximum.accumulate(np.maximum(p, 0), axis=1)
        out[rows] = (p * np.repeat(level, HORIZON)[:, None]).reshape(len(rows), HORIZON, 3)
        return out

    def scheduled(self, t: int) -> tuple[np.ndarray, list]:
        """Known outflows in (t, t+H]: recurring payments, rent cheques, VAT. Positive numbers."""
        n = self.led.base.shape[0]
        H = HORIZON
        out = np.zeros((n, H))
        items = []
        idx = self.led.idx
        for k, df in self.recurring.items():
            past = df[df.t <= t]
            if past.empty:
                continue
            last = past.groupby("sme").tail(1)
            for sme, tl, amt in zip(last.sme.values, last.t.values, last.amount.values):
                if t - tl > 45:
                    continue
                d0 = START + timedelta(days=int(tl))
                for k_m in (1, 2):
                    y, m = d0.year + (d0.month - 1 + k_m) // 12, (d0.month - 1 + k_m) % 12 + 1
                    try:
                        nd_ = d0.replace(year=y, month=m)
                    except ValueError:
                        nd_ = (d0.replace(day=1, year=y, month=m) + pd.offsets.MonthEnd(0)).date()
                    while nd_.weekday() >= 5 and k == "payroll":
                        nd_ -= timedelta(days=1)
                    h = (nd_ - START).days - t
                    if 1 <= h <= H:
                        out[idx[sme], h - 1] += -amt
                        items.append((idx[sme], h, k, float(-amt)))
        r = self.rent[(self.rent.t > t) & (self.rent.t <= t + H)]
        for i, tr, amt in zip(r.i.values, r.t.values, r.amount.values):
            out[i, tr - t - 1] += amt
            items.append((int(i), int(tr - t), "rent_cheque", float(amt)))
        # VAT: next quarterly return inside the window, estimated from the quarter's activity so far
        d = START + timedelta(days=t)
        for qoff in (0, -1):
            qs = pd.Period(pd.Timestamp(d), "Q") + qoff
            due = (qs.end_time + pd.Timedelta(days=28)).date()
            h = (due - START).days - t
            if not 1 <= h <= H:
                continue
            q0, q1 = day_index(qs.start_time.date()), min(day_index(qs.end_time.date()), t)
            frac = (q1 - q0 + 1) / (day_index(qs.end_time.date()) - q0 + 1)
            sales_q = self.kind_mats["sales"][:, q0:q1 + 1].sum(axis=1)
            inv = self.led.inv
            iq = inv[(inv.t_issue >= q0) & (inv.t_issue <= q1)]
            rev = np.zeros(n)
            np.add.at(rev, iq.payee_i[iq.payee_i >= 0].values, iq.amount[iq.payee_i >= 0].values)
            pur = np.zeros(n)
            np.add.at(pur, iq.payer_i[iq.payer_i >= 0].values, iq.amount[iq.payer_i >= 0].values)
            vat = np.maximum(0.0, 0.05 * (sales_q + rev - pur)) / max(frac, 0.25)
            out[:, h - 1] += vat
            items += [(i, h, "vat", float(v)) for i, v in enumerate(vat) if v > 0]
        return out, items

    def running(self, t: int) -> np.ndarray:
        rc = -self.kind_mats["running_costs"]
        lo = max(0, t - 27)
        block = rc[:, lo:t + 1]
        wk = (np.arange(lo, t + 1) + START.weekday()) % 7 >= 5
        wd_mean = block[:, ~wk].mean(axis=1) if (~wk).any() else np.zeros(rc.shape[0])
        we_mean = block[:, wk].mean(axis=1) if wk.any() else wd_mean
        tt = t + np.arange(1, HORIZON + 1)
        is_we = self.cal["dow"][tt] >= 5
        return np.where(is_we[None, :], we_mean[:, None], wd_mean[:, None])

    # ---------------- the forecast ----------------
    def forecast(self, t: int, ledger: Ledger | None = None, n_paths: int = N_PATHS, seed: int = 0,
                 sales_factor: np.ndarray | None = None, extra_out: np.ndarray | None = None,
                 delay_shift: dict | None = None) -> Forecast:
        """Probabilistic forecast at day t. What-if hooks: `sales_factor` [n] scales expected sales,
        `extra_out` [n, H] adds one-off outflows, `delay_shift` {(payee_i, payer): days} delays receipts."""
        led = ledger or self.led
        rng = np.random.default_rng(seed + t)
        n = led.base.shape[0]
        H = HORIZON
        bal = led.balance[:, t].copy()
        sales = self.predict_sales(t)
        if sales_factor is not None:
            sales = sales * sales_factor[:, None, None]
        sched, items = self.scheduled(t)
        if extra_out is not None:
            sched = sched + extra_out
        run = self.running(t)

        open_ = led.open_invoices(t).copy()
        if "agreed" not in open_.columns:
            open_["agreed"] = False
        q = self.predict_delay(open_, t)
        agreed = open_.agreed.fillna(False).values.astype(bool)
        # an agreed (grace-period) settlement date is known exactly
        q[agreed] = (open_.t_settle.values[agreed] - t)[:, None]
        if delay_shift:
            for (pi, payer), d in delay_shift.items():
                m = (open_.payee_i.values == pi) & ((open_.payer.values == payer) | (payer == "*")) & ~agreed
                q[m] += d
        open_["r10"], open_["r50"], open_["r90"] = q[:, 0], q[:, 1], q[:, 2]

        pay = open_[open_.payer_i >= 0]
        payables = np.zeros((n, H))
        hh = np.rint(pay.r50.values).astype(int)
        m = hh <= H
        np.add.at(payables, (pay.payer_i.values[m], hh[m] - 1), pay.amount.values[m])

        recv = open_[open_.payee_i >= 0]
        recv50 = np.zeros((n, H))
        hh = np.rint(recv.r50.values).astype(int)
        m = hh <= H
        np.add.at(recv50, (recv.payee_i.values[m], hh[m] - 1), recv.amount.values[m])

        # Monte Carlo: sales with a business-level common shock, receipts with independent timing
        P = n_paths
        z_common = rng.standard_normal((P, n, 1))
        z_day = rng.standard_normal((P, n, H))
        z = np.sqrt(0.5) * z_common + np.sqrt(0.5) * z_day
        s10, s50, s90 = sales[..., 0], sales[..., 1], sales[..., 2]
        sal = s50[None] + np.where(z > 0, (s90 - s50)[None], (s50 - s10)[None]) * z / Z90
        sal = np.maximum(sal, 0)

        # every open invoice gets one sampled settlement day per path, shared by payer and payee
        rec = np.zeros((P, n, H))
        pay_p = np.zeros((P, n, H))
        if len(open_):
            zi = rng.standard_normal((P, len(open_)))
            r50, r10, r90 = open_.r50.values, open_.r10.values, open_.r90.values
            days = r50[None] + np.where(zi > 0, (r90 - r50)[None], (r50 - r10)[None]) * zi / Z90
            days = np.clip(np.rint(days), 1, 10_000).astype(int)
            days[:, agreed] = np.rint(r50[agreed]).astype(int)
            pi, ii = np.nonzero(days <= H)
            amt = open_.amount.values[ii]
            payee, payer = open_.payee_i.values[ii], open_.payer_i.values[ii]
            m = payee >= 0
            np.add.at(rec, (pi[m], payee[m], days[pi[m], ii[m]] - 1), amt[m])
            m = payer >= 0
            np.add.at(pay_p, (pi[m], payer[m], days[pi[m], ii[m]] - 1), amt[m])

        net = sal + rec - pay_p - (sched + run)[None]
        paths = bal[None, :, None] + np.cumsum(net, axis=2)          # [P, n, H]
        if self.spread is not None:  # split-conformal widening per horizon, fitted on a calibration window
            med = np.median(paths, axis=0, keepdims=True)
            paths = med + self.spread[None, None, :] * (paths - med)
        mins = paths.min(axis=2)
        neg = paths < 0
        p_short = neg.any(axis=2).mean(axis=0)
        first = np.where(neg.any(axis=2), neg.argmax(axis=2) + 1, 0).astype(float)
        first[first == 0] = np.nan
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", RuntimeWarning)
            first_day = np.nan_to_num(np.nanmedian(first, axis=0), nan=0.0)
        gap80 = np.maximum(0, -np.quantile(mins, 0.2, axis=0))
        qs = np.quantile(paths, [0.1, 0.5, 0.9], axis=0)
        return Forecast(t=t, p_short=p_short, first_day=first_day, gap80=gap80, q10=qs[0], q50=qs[1], q90=qs[2],
                        balance=bal, sched=sched, sales50=s50, running=run, payables=payables, recv50=recv50,
                        open_recv=recv, open_pay=pay, sched_items=items)
