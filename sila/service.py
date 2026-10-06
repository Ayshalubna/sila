"""Read models and actions behind the web app and API.

The live demo shows the network on TODAY as if Sila were switched on this morning; the six-month
backtest (Apr-Sep 2026) is the evidence for what it does over time. Each visitor gets a private sandbox: decisions on today's suggested moves only change that visitor's
copy of the ledger, so a public demo can be used by many people at once.
"""
from __future__ import annotations

import json
import math
import os
import sqlite3
import threading
import time
from collections import OrderedDict
from dataclasses import dataclass, field
from datetime import datetime, timezone
from functools import lru_cache
from pathlib import Path

import numpy as np
import pandas as pd

from . import synth
from .config import (
    ARTIFACTS,
    EARLY_PAY_RATE_30D,
    GRACE_DAYS,
    HORIZON,
    ILLUSTRATIVE_LOAN_APR,
    MAX_MOVE_SHARE,
    MIN_MOVE,
    PAYER_BUFFER_DAYS,
    REPLAY_START,
    ROOT,
    TODAY,
    TRAIN_END,
)
from .forecast import DELAY_LABELS, Forecast, Forecaster, delay_features
from .ledger import Ledger, day_index, shortfall_episodes, to_date
from .mesh import ALERT_P, Mesh, Move

WATCH_P = 0.1
DB_PATH = Path(os.getenv("SILA_DB", "/tmp/sila_audit.db"))
MAX_SESSIONS = 300
EVAL_PATH = ROOT / "eval" / "results.json"

KIND_LABEL = {"payroll": "WPS payroll", "rent_cheque": "Rent cheque", "vat": "VAT return", "utilities": "Utilities",
              "owner_drawings": "Owner drawings", "running_costs": "Running costs", "supplier": "Supplier invoice"}


def status_of(p: float, bal: float) -> str:
    if bal < 0:
        return "short"
    if p >= ALERT_P:
        return "at_risk"
    if p >= WATCH_P:
        return "watch"
    return "safe"


def _r(x, nd=0):
    x = float(x)
    return round(x, nd) if nd else int(round(x))


# ---------------------------------------------------------------------------------------------
@dataclass
class Session:
    sid: str
    ledger: Ledger | None = None
    fc: Forecast | None = None
    decisions: dict = field(default_factory=dict)     # move id -> {"helped": str|None, "helper": str|None}
    touched: float = field(default_factory=time.time)


class Audit:
    def __init__(self, path: Path = DB_PATH):
        self.path = path
        self.lock = threading.Lock()
        with self._con() as c:
            c.execute("""CREATE TABLE IF NOT EXISTS decisions (ts TEXT, session TEXT, move TEXT, party TEXT,
                         business TEXT, decision TEXT, result TEXT)""")

    def _con(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        return sqlite3.connect(self.path)

    def log(self, session: str, move: str, party: str, business: str, decision: str, result: str) -> None:
        with self.lock, self._con() as c:
            c.execute("INSERT INTO decisions VALUES (?,?,?,?,?,?,?)",
                      (datetime.now(timezone.utc).isoformat(timespec="seconds"), session, move, party, business,
                       decision, result))

    def events(self, session: str) -> list[dict]:
        with self._con() as c:
            rows = c.execute("SELECT ts, move, party, business, decision, result FROM decisions WHERE session=? "
                             "ORDER BY rowid", (session,)).fetchall()
        return [dict(zip(("ts", "move", "party", "business", "decision", "result"), r)) for r in rows]


class Sila:
    def __init__(self):
        tic = time.time()
        self.world = synth.ensure()
        self.base = Ledger.build(self.world)
        self.F = Forecaster(self.base).load()
        self.state = self.base
        self.t = day_index(TODAY)
        self.fc = self.F.forecast(self.t, ledger=self.state)
        self.mesh = Mesh(self.F)
        props = self.mesh.propose(self.fc, ledger=self.state)
        self.advisories = list(self.mesh.advisories)
        props, self.fc_all = self.mesh.verify(self.t, self.state, props, self.fc)
        self.moves: dict[str, Move] = {m.id: m for m in props}
        self.smes = {s["id"]: s for s in self.world.smes}
        self.ext = {e["id"]: e for e in self.world.externals}
        self.ids = self.base.ids
        self.idx = self.base.idx
        self.layout = self._layout()
        self.replay_log = json.loads((ARTIFACTS / "replay_log.json").read_text())
        self.replay_metrics = json.loads((ARTIFACTS / "replay_metrics.json").read_text())
        self.sessions: OrderedDict[str, Session] = OrderedDict()
        self.lock = threading.Lock()
        self.audit = Audit()
        self.boot_seconds = round(time.time() - tic, 2)

    # ------------------------------------------------------------------ helpers
    def name(self, pid: str) -> dict:
        if pid in self.smes:
            s = self.smes[pid]
            return {"id": pid, "name": s["name"], "name_ar": s["name_ar"], "network": True}
        e = self.ext.get(pid, {"name": pid})
        return {"id": pid, "name": e["name"], "name_ar": None, "network": False}

    def date(self, h: float) -> str:
        return to_date(self.t + int(round(h))).isoformat()

    def session(self, sid: str | None) -> Session:
        sid = sid or "public"
        with self.lock:
            s = self.sessions.get(sid)
            if s is None:
                s = Session(sid)
                self.sessions[sid] = s
                while len(self.sessions) > MAX_SESSIONS:
                    self.sessions.popitem(last=False)
            self.sessions.move_to_end(sid)
            s.touched = time.time()
            return s

    def view(self, sid: str | None) -> tuple[Ledger, Forecast, Session]:
        s = self.session(sid)
        if s.ledger is None:
            return self.state, self.fc, s
        return s.ledger, s.fc, s

    def move_status(self, m: Move, s: Session) -> str:
        d = s.decisions.get(m.id, {})
        if "decline" in (d.get("helped"), d.get("helper")):
            return "declined"
        if d.get("helped") == "accept" and d.get("helper") == "accept":
            return "agreed"
        if d.get("helped") == "accept" or d.get("helper") == "accept":
            return "waiting"
        return "proposed"

    # ------------------------------------------------------------------ layout
    def _layout(self) -> dict:
        """Sector 'constellations' on a ring; businesses in a sunflower pattern inside each one."""
        sectors = list(synth.SECTORS)
        pos = {}
        golden = math.pi * (3 - math.sqrt(5))
        for k, sec in enumerate(sectors):
            ang = -math.pi / 2 + 2 * math.pi * k / len(sectors)
            cx, cy = 500 + 330 * math.cos(ang), 500 + 330 * math.sin(ang)
            members = sorted([s for s in self.world.smes if s["sector"] == sec], key=lambda s: -s["monthly_revenue"])
            for j, s in enumerate(members):
                r = 15.5 * math.sqrt(j + 0.5)
                a = j * golden
                pos[s["id"]] = (round(cx + r * math.cos(a), 1), round(cy + r * math.sin(a), 1))
        centers = {sec: (round(500 + 330 * math.cos(-math.pi / 2 + 2 * math.pi * k / len(sectors)), 1),
                         round(500 + 330 * math.sin(-math.pi / 2 + 2 * math.pi * k / len(sectors)), 1))
                   for k, sec in enumerate(sectors)}
        return {"pos": pos, "centers": centers}

    # ------------------------------------------------------------------ overview
    def overview(self, sid: str | None = None) -> dict:
        led, fc, s = self.view(sid)
        st = [status_of(p, b) for p, b in zip(fc.p_short, fc.balance)]
        moves = list(self.moves.values())
        agreed = [m for m in moves if self.move_status(m, s) == "agreed"]
        rp = self.replay_metrics
        ev = self.eval_results()
        at_risk = [i for i, x in enumerate(st) if x == "at_risk"]
        return {
            "today": TODAY.isoformat(), "businesses": len(self.ids), "sectors": len(synth.SECTORS),
            "emirates": len({s["emirate"] for s in self.world.smes}),
            "network_links": sum(len(s["network_suppliers"]) for s in self.world.smes),
            "status_counts": {k: st.count(k) for k in ("safe", "watch", "at_risk", "short")},
            "cash_at_risk": _r(sum(fc.gap80[i] for i in at_risk), 0),
            "moves_today": len(moves), "moves_agreed": len(agreed),
            "cover_today": _r(sum(m.amount for m in moves)),
            "businesses_helped_today": len({m.helps for m in moves}),
            "advisories": len(self.advisories),
            "replay": {k: rp[k] for k in ("episodes_prevented_share", "episode_days_avoided_share", "moves_accepted",
                                           "aed_moved", "helpers_pushed_into_shortfall", "saving_vs_loan",
                                           "businesses_helped", "episodes_prevented", "episodes_baseline",
                                           "new_debt_created", "fees_paid", "loan_cost_equivalent")},
            "eval": {"auc": ev.get("alerts", {}).get("auc"), "recall": ev.get("alerts", {}).get("recall"),
                     "precision": ev.get("alerts", {}).get("precision"),
                     "median_lead_days": ev.get("alerts", {}).get("median_lead_days"),
                     "warned_share": ev.get("alerts", {}).get("warned_share"),
                     "coverage": ev.get("calibration", {}).get("coverage_p10_p90")},
            "settings": {"alert_p": ALERT_P, "buffer_days": PAYER_BUFFER_DAYS, "max_share": MAX_MOVE_SHARE,
                         "early_pay_rate_30d": EARLY_PAY_RATE_30D, "grace_days": GRACE_DAYS, "min_move": MIN_MOVE,
                         "loan_apr": ILLUSTRATIVE_LOAN_APR, "horizon": HORIZON,
                         "train_end": TRAIN_END.isoformat(), "replay_start": REPLAY_START.isoformat()},
        }

    @lru_cache(maxsize=1)
    def eval_results(self) -> dict:
        try:
            return json.loads(EVAL_PATH.read_text())
        except (OSError, ValueError):
            return {}

    # ------------------------------------------------------------------ businesses
    def _row(self, i: int, fc: Forecast) -> dict:
        s = self.world.smes[i]
        sid = s["id"]
        n_moves = sum(1 for m in self.moves.values() if sid in (m.helps, m.helper))
        q = fc.q50[i]
        return {
            "id": sid, "name": s["name"], "name_ar": s["name_ar"], "owner": s["owner"],
            "sector": s["sector"], "sector_label": s["sector_label"], "sector_label_ar": s["sector_label_ar"],
            "emirate": s["emirate"], "emirate_ar": s["emirate_ar"], "monthly_revenue": s["monthly_revenue"],
            "staff": s["staff"], "balance": _r(fc.balance[i]), "p_short": round(float(fc.p_short[i]), 3),
            "first_day": int(fc.first_day[i]), "first_date": self.date(fc.first_day[i]) if fc.first_day[i] else None,
            "gap": _r(fc.gap80[i], 0), "status": status_of(fc.p_short[i], fc.balance[i]),
            "spark": [_r(x) for x in q[::2]], "partners": len(s["network_suppliers"]) + len(s["network_customers"]),
            "moves_today": n_moves,
        }

    def businesses(self, sid=None, q="", sector="", emirate="", status="", sort="risk", page=1, size=25) -> dict:
        _, fc, _ = self.view(sid)
        rows = [self._row(i, fc) for i in range(len(self.ids))]
        if q:
            ql = q.lower()
            rows = [r for r in rows if ql in r["name"].lower() or q in r["name_ar"] or ql in r["id"].lower()
                    or ql in r["owner"].lower()]
        if sector:
            rows = [r for r in rows if r["sector"] == sector]
        if emirate:
            rows = [r for r in rows if r["emirate"] == emirate]
        if status:
            rows = [r for r in rows if r["status"] == status]
        key = {"risk": lambda r: (-r["p_short"], r["first_day"] or 99), "name": lambda r: r["name"],
               "balance": lambda r: r["balance"], "revenue": lambda r: -r["monthly_revenue"]}[sort]
        rows.sort(key=key)
        total = len(rows)
        page = max(1, page)
        return {"total": total, "page": page, "size": size, "rows": rows[(page - 1) * size: page * size],
                "sectors": [{"id": k, "label": v["label"], "label_ar": v["label_ar"]} for k, v in synth.SECTORS.items()],
                "emirates": sorted({(s["emirate"], s["emirate_ar"]) for s in self.world.smes})}

    def business(self, bid: str, sid=None) -> dict:
        led, fc, s = self.view(sid)
        i = self.idx[bid]
        row = self._row(i, fc)
        sme = self.smes[bid]
        H = HORIZON
        hist_from = self.t - 89
        history = [{"d": to_date(t).isoformat(), "v": _r(led.balance[i, t])} for t in range(hist_from, self.t + 1)]
        fan = [{"d": self.date(h + 1), "q10": _r(fc.q10[i, h]), "q50": _r(fc.q50[i, h]), "q90": _r(fc.q90[i, h])}
               for h in range(H)]
        # ---- upcoming money in / out
        items = []
        for (j, h, kind, amt) in fc.sched_items:
            if j == i:
                items.append({"dir": "out", "kind": kind, "label": KIND_LABEL.get(kind, kind), "amount": _r(amt),
                              "day": h, "date": self.date(h), "certain": kind in ("payroll", "rent_cheque")})
        pay = fc.open_pay[fc.open_pay.payer_i == i]
        for _, r in pay.iterrows():
            if r.r50 <= H:
                items.append({"dir": "out", "kind": "supplier", "label": "Supplier invoice", "amount": _r(r.amount),
                              "day": int(round(r.r50)), "date": self.date(r.r50), "counterparty": self.name(r.payee),
                              "invoice": r.invoice_id, "due": pd.Timestamp(r.due).date().isoformat(),
                              "agreed": bool(r.agreed)})
        recv = fc.open_recv[fc.open_recv.payee_i == i].sort_values("r50")
        receivables = []
        for _, r in recv.iterrows():
            due_h = int(r.t_due) - self.t
            receivables.append({
                "invoice": r.invoice_id, "counterparty": self.name(r.payer), "amount": _r(r.amount),
                "due": pd.Timestamp(r.due).date().isoformat(), "due_day": due_h,
                "expected": self.date(r.r50), "expected_day": int(round(r.r50)),
                "early": self.date(r.r10), "late": self.date(r.r90),
                "days_late": int(round(r.r50 - due_h)), "in_window": bool(r.r50 <= H), "agreed": bool(r.agreed)})
            if r.r50 <= H:
                items.append({"dir": "in", "kind": "receipt", "label": "Customer payment", "amount": _r(r.amount),
                              "day": int(round(r.r50)), "date": self.date(r.r50), "counterparty": self.name(r.payer),
                              "invoice": r.invoice_id, "due": pd.Timestamp(r.due).date().isoformat(),
                              "agreed": bool(r.agreed), "range": [self.date(r.r10), self.date(r.r90)]})
        sales28 = float(fc.sales50[i].sum())
        items.sort(key=lambda x: (x["day"], x["dir"]))
        # ---- why: what drives the first crunch
        why = self._why(i, fc, items, sales28)
        moves = [self.move_view(m, s) for m in self.moves.values()
                 if bid in (m.helps, m.helper) or any(bid in (lg.payer, lg.payee) for lg in m.legs)]
        adv = next((a.__dict__ for a in self.advisories if a.business == bid), None)
        partners = []
        for pid, rel in [(p, "supplier") for p in sme["network_suppliers"]] + [(c, "customer") for c in sme["network_customers"]]:
            j = self.idx[pid]
            partners.append({**self.name(pid), "relation": rel, "status": status_of(fc.p_short[j], fc.balance[j]),
                             "sector_label": self.smes[pid]["sector_label"], "sector_label_ar": self.smes[pid]["sector_label_ar"]})
        hist_moves = [m for m in self.replay_log if m["status"] == "accepted" and
                      (m["helps"] == bid or m["helper"] == bid or any(bid in (lg["payer"], lg["payee"]) for lg in m["legs"]))]
        return {**row, "profile": {k: sme[k] for k in ("owner", "owner_ar", "payroll_day", "rent_cheques", "staff",
                                                        "monthly_revenue")},
                "history": history, "fan": fan, "items": items, "receivables": receivables[:40],
                "sales_28d": _r(sales28), "why": why, "moves": moves, "advisory": adv, "partners": partners,
                "sila_history": {
                    "helped": sum(1 for m in hist_moves if m["helps"] == bid),
                    "helped_aed": _r(sum(m["amount"] for m in hist_moves if m["helps"] == bid)),
                    "helper": sum(1 for m in hist_moves if m["helps"] != bid),
                    "helper_aed": _r(sum(m["amount"] for m in hist_moves if m["helps"] != bid)),
                    "recent": [self._hist_item(m, bid) for m in hist_moves[-6:]][::-1]}}

    def _hist_item(self, m: dict, bid: str) -> dict:
        other = m["helper"] if m["helps"] == bid else m["helps"]
        return {"date": m["date"], "kind": m["kind"], "role": "helped" if m["helps"] == bid else "helper",
                "counterparty": self.name(other), "amount": _r(m["amount"]), "fee": m["fee"]}

    def _why(self, i: int, fc: Forecast, items: list, sales28: float) -> dict:
        H = HORIZON
        crunch = int(fc.first_day[i]) or int(np.argmin(fc.q50[i])) + 1
        outs = sorted([x for x in items if x["dir"] == "out" and x["day"] <= crunch], key=lambda x: -x["amount"])[:3]
        late = sorted([r for r in fc.open_recv[fc.open_recv.payee_i == i].itertuples()
                       if r.t_due - self.t <= crunch and r.r50 > crunch], key=lambda r: -r.amount)[:2]
        late_items = [{"counterparty": self.name(r.payer), "amount": _r(r.amount),
                       "due": pd.Timestamp(r.due).date().isoformat(), "expected": self.date(r.r50),
                       "invoice": r.invoice_id} for r in late]
        recent = float(self.F.kind_mats["sales"][i, self.t - H + 1:self.t + 1].sum())
        sales_change = (sales28 / recent - 1) if recent > 1_000 else None
        return {"crunch_day": crunch, "crunch_date": self.date(crunch), "lowest": _r(fc.q50[i].min()),
                "lowest_date": self.date(int(np.argmin(fc.q50[i])) + 1), "big_outflows": outs, "late_receipts": late_items,
                "sales_change": None if sales_change is None else round(sales_change, 3),
                "balance": _r(fc.balance[i])}

    # ------------------------------------------------------------------ moves
    def move_view(self, m: Move, s: Session) -> dict:
        d = s.decisions.get(m.id, {})
        legs = []
        for lg in m.legs:
            legs.append({"invoice": lg.invoice_id, "payer": self.name(lg.payer), "payee": self.name(lg.payee),
                         "amount": _r(lg.amount), "from_date": self.date(lg.from_day), "to_date": self.date(lg.to_day),
                         "days_moved": abs(lg.from_day - lg.to_day), "fee": round(lg.fee, 2)})
        return {"id": m.id, "kind": m.kind, "helps": self.name(m.helps), "helper": self.name(m.helper),
                "amount": _r(m.amount), "fee": round(m.fee, 2), "loan_cost": round(m.loan_cost, 2),
                "shortfall_date": self.date(m.shortfall_day), "shortfall_day": m.shortfall_day,
                "helper_buffer_days": m.helper_buffer_days, "cover_days": m.cover_days, "legs": legs,
                "verified": m.verified, "status": self.move_status(m, s),
                "decisions": {"helped": d.get("helped"), "helper": d.get("helper")}}

    def moves_today(self, sid=None) -> dict:
        _, fc, s = self.view(sid)
        mv = [self.move_view(m, s) for m in self.moves.values()]
        mv.sort(key=lambda x: (x["shortfall_day"], -x["amount"]))
        adv = []
        for a in self.advisories:
            i = self.idx[a.business]
            adv.append({**a.__dict__, "business": self.name(a.business), "date": self.date(a.shortfall_day),
                        "p_short": round(float(fc.p_short[i]), 3)})
        plans = {}
        for x in mv:
            p = plans.setdefault(x["helps"]["id"], {"business": x["helps"], "moves": [], "amount": 0, "fee": 0.0,
                                                     "shortfall_date": x["shortfall_date"],
                                                     "p_before": x["verified"].get("p_short_before"),
                                                     "p_after": x["verified"].get("p_short_after"),
                                                     "gap_before": x["verified"].get("gap_before"),
                                                     "gap_after": x["verified"].get("gap_after")})
            p["moves"].append(x["id"])
            p["amount"] += x["amount"]
            p["fee"] = round(p["fee"] + x["fee"], 2)
            p["shortfall_date"] = min(p["shortfall_date"], x["shortfall_date"])
        for p in plans.values():
            i = self.idx[p["business"]["id"]]
            p["status_now"] = status_of(fc.p_short[i], fc.balance[i])
            p["p_now"] = round(float(fc.p_short[i]), 3)
            p["balance"] = _r(fc.balance[i])
            p["sector_label"] = self.smes[p["business"]["id"]]["sector_label"]
            p["sector_label_ar"] = self.smes[p["business"]["id"]]["sector_label_ar"]
        return {"moves": mv, "advisories": adv, "plans": sorted(plans.values(), key=lambda p: (p["shortfall_date"], -p["amount"])),
                "summary": {"proposed": len(mv), "agreed": sum(x["status"] == "agreed" for x in mv),
                            "cover": _r(sum(x["amount"] for x in mv)), "fees": round(sum(x["fee"] for x in mv), 2),
                            "loan_cost": round(sum(x["loan_cost"] for x in mv), 2)}}

    def decide(self, sid: str, move_id: str, party: str, decision: str) -> dict:
        m = self.moves.get(move_id)
        if m is None:
            raise KeyError(move_id)
        s = self.session(sid)
        bid = m.helps if party == "helped" else m.helper
        with self.lock:
            prev = self.move_status(m, s)
            if prev in ("agreed", "declined"):
                return {"move": self.move_view(m, s), "changed": False, "message": f"already {prev}"}
            s.decisions.setdefault(m.id, {})[party] = decision
            status = self.move_status(m, s)
            impact = None
            if status == "agreed":
                agreed = [x for x in self.moves.values() if self.move_status(x, s) == "agreed"]
                before = s.fc or self.fc
                led = Mesh.apply(self.state.copy(), agreed, self.t)
                s.ledger = led
                s.fc = self.F.forecast(self.t, ledger=led)
                hi, ii = self.idx[m.helper], self.idx[m.helps]
                impact = {"helps": {"before": round(float(before.p_short[ii]), 3), "after": round(float(s.fc.p_short[ii]), 3),
                                    "status": status_of(s.fc.p_short[ii], s.fc.balance[ii])},
                          "helper": {"before": round(float(before.p_short[hi]), 3), "after": round(float(s.fc.p_short[hi]), 3),
                                     "status": status_of(s.fc.p_short[hi], s.fc.balance[hi])}}
        self.audit.log(s.sid, m.id, party, bid, decision, status)
        return {"move": self.move_view(m, s), "changed": True, "impact": impact}

    def reset(self, sid: str) -> None:
        with self.lock:
            self.sessions.pop(sid, None)

    # ------------------------------------------------------------------ what-if
    def whatif(self, sid: str | None, bid: str, sales_change: float = 0.0, late_days: int = 0, late_payer: str = "*",
               expense: float = 0.0, expense_day: int = 7) -> dict:
        led, fc, _ = self.view(sid)
        i = self.idx[bid]
        n = len(self.ids)
        sf = np.ones(n)
        sf[i] = 1 + sales_change
        extra = None
        if expense > 0:
            extra = np.zeros((n, HORIZON))
            extra[i, min(max(expense_day, 1), HORIZON) - 1] = expense
        shift = {(i, late_payer): late_days} if late_days else None
        sc = self.F.forecast(self.t, ledger=led, sales_factor=sf, extra_out=extra, delay_shift=shift)

        def pack(f: Forecast) -> dict:
            return {"p_short": round(float(f.p_short[i]), 3), "first_date": self.date(f.first_day[i]) if f.first_day[i] else None,
                    "gap": _r(f.gap80[i]), "lowest": _r(f.q50[i].min()), "status": status_of(f.p_short[i], f.balance[i]),
                    "fan": [{"d": self.date(h + 1), "q10": _r(f.q10[i, h]), "q50": _r(f.q50[i, h]), "q90": _r(f.q90[i, h])}
                            for h in range(HORIZON)]}
        return {"business": self.name(bid), "base": pack(fc), "scenario": pack(sc)}

    # ------------------------------------------------------------------ invoice timing explanation
    def invoice_why(self, invoice_id: str, sid=None) -> dict:
        led, fc, _ = self.view(sid)
        op = led.open_invoices(self.t)
        op = op[op.invoice_id == invoice_id]
        if op.empty:
            raise KeyError(invoice_id)
        tt = np.full(len(op), self.t)
        X = delay_features(op, tt, self.F.hist, self.F.cal)
        contrib = self.F.delay_models[0.5].predict(X, pred_contrib=True)[0]
        base = float(self.F.baseline_delay(op, tt)[0])
        q = self.F.predict_delay(op, self.t)[0]
        r = op.iloc[0]
        feats = sorted([(DELAY_LABELS.get(c, c), float(v), float(X.iloc[0][c])) for c, v in zip(X.columns, contrib[:-1])],
                       key=lambda x: -abs(x[1]))[:5]
        st = self.F.hist.stats(op.payer.values, tt)[0]
        return {"invoice": invoice_id, "payer": self.name(r.payer), "payee": self.name(r.payee), "amount": _r(r.amount),
                "due": pd.Timestamp(r.due).date().isoformat(), "due_day": int(r.t_due) - self.t,
                "payer_avg_delay": None if np.isnan(st[1]) else round(float(st[1]), 1),
                "payer_history": 0 if np.isnan(st[0]) else int(st[0]),
                "baseline_days": round(base, 1), "adjustment": round(float(q[1] - base), 1),
                "expected": self.date(q[1]), "range": [self.date(q[0]), self.date(q[2])],
                "drivers": [{"feature": f, "days": round(v, 1), "value": round(x, 2)} for f, v, x in feats]}

    # ------------------------------------------------------------------ network
    @lru_cache(maxsize=1)
    def _edges(self) -> list[dict]:
        inv = self.base.inv
        recent = inv[(inv.t_issue > self.t - 180) & (inv.t_issue <= self.t) & (inv.payer_i >= 0) & (inv.payee_i >= 0)]
        vol = recent.groupby(["payee", "payer"]).amount.sum()
        return [{"s": a, "c": b, "v": _r(v)} for (a, b), v in vol.items() if v > 0]

    def network(self, sid=None) -> dict:
        _, fc, s = self.view(sid)
        nodes = []
        for i, sme in enumerate(self.world.smes):
            x, y = self.layout["pos"][sme["id"]]
            nodes.append({"id": sme["id"], "name": sme["name"], "name_ar": sme["name_ar"], "sector": sme["sector"],
                          "x": x, "y": y, "r": round(3.4 + 2.0 * math.sqrt(sme["monthly_revenue"] / 100_000), 2),
                          "status": status_of(fc.p_short[i], fc.balance[i]), "p": round(float(fc.p_short[i]), 2)})
        flows = [{"id": m.id, "from": lg.payer if lg.to_day < lg.from_day else lg.payee,
                  "to": lg.payee if lg.to_day < lg.from_day else lg.payer, "kind": m.kind, "amount": _r(lg.amount),
                  "status": self.move_status(m, s)} for m in self.moves.values() for lg in m.legs]
        centers = [{"id": k, "label": v["label"], "label_ar": v["label_ar"], "x": self.layout["centers"][k][0],
                    "y": self.layout["centers"][k][1]} for k, v in synth.SECTORS.items()]
        return {"nodes": nodes, "edges": self._edges(), "flows": flows, "sectors": centers}

    # ------------------------------------------------------------------ proof
    @lru_cache(maxsize=1)
    def proof(self) -> dict:
        t0, t1 = day_index(REPLAY_START), self.t
        rb = np.load(ARTIFACTS / "replay_balance.npy")
        start_neg = self.base.balance[:, t0 - 1] < 0
        keep = ~start_neg
        weeks = []
        log = [m for m in self.replay_log if m["status"] == "accepted"]
        log_t = np.array([day_index(m["date"]) for m in log])
        for w0 in range(t0, t1, 7):
            w1 = min(w0 + 7, t1)
            sel = (log_t >= w0) & (log_t < w1)
            weeks.append({"week": to_date(w0).isoformat(),
                          "short_without": int((self.base.balance[keep, w0:w1] < 0).sum()),
                          "short_with": int((rb[keep, w0:w1] < 0).sum()),
                          "moves": int(sel.sum()), "aed": _r(sum(log[k]["amount"] for k in np.where(sel)[0]))})
        stories = []
        for i, st, depth in sorted(shortfall_episodes(self.base.balance, t0, t1), key=lambda e: e[2]):
            if start_neg[i]:
                continue
            en = st
            while en < self.base.balance.shape[1] and self.base.balance[i, en] < 0:
                en += 1
            if not (rb[i, st:en] >= 0).all():
                continue
            bid = self.ids[i]
            mv = [m for m in log if m["helps"] == bid and st - HORIZON <= day_index(m["date"]) < st]
            if not mv or st - day_index(mv[0]["date"]) < 7:
                continue
            stories.append({"business": self.name(bid), "sector_label": self.smes[bid]["sector_label"],
                            "sector_label_ar": self.smes[bid]["sector_label_ar"],
                            "would_be_short": to_date(st).isoformat(), "days": en - st, "depth": _r(depth),
                            "warned_on": mv[0]["date"], "lead_days": st - day_index(mv[0]["date"]),
                            "moves": [{"date": m["date"], "kind": m["kind"], "helper": self.name(m["helper"]),
                                       "amount": _r(m["amount"]), "fee": m["fee"]} for m in mv[:4]],
                            "balance_without": [_r(x) for x in self.base.balance[i, st - 21:en + 7]],
                            "balance_with": [_r(x) for x in rb[i, st - 21:en + 7]],
                            "start": to_date(st - 21).isoformat()})
            if len(stories) == 4:
                break
        return {"eval": self.eval_results(), "replay": self.replay_metrics, "weeks": weeks, "stories": stories}

    def warm_up(self) -> None:
        self.proof()
        self._edges()
        self.business(self.ids[0])


_INSTANCE: Sila | None = None
_INSTANCE_LOCK = threading.Lock()


def get() -> Sila:
    global _INSTANCE
    if _INSTANCE is None:
        with _INSTANCE_LOCK:
            if _INSTANCE is None:
                _INSTANCE = Sila()
    return _INSTANCE
