"""Deterministic synthetic UAE small-business network.

Generates 240 SMEs across 10 sectors and 7 emirates with ~21 months of daily cash flows:
walk-in sales, B2B invoices (with realistic late payment), supplier bills, WPS payroll,
post-dated rent cheques, quarterly VAT and utilities. Businesses trade with each other,
which is what lets Sila move money inside the network.

Everything is synthetic. No real business, person or bank data is used.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date, timedelta

import numpy as np
import pandas as pd

from .config import ARTIFACTS, EID, RAMADAN, START, TODAY

SEED = 7
PRE = 150  # days of pre-history for invoices (so receivables/payables exist on day one)

FIRST_NAMES = [
    ("Layla", "ليلى"), ("Omar", "عمر"), ("Sara", "سارة"), ("Zaid", "زيد"), ("Maryam", "مريم"),
    ("Hassan", "حسن"), ("Nadia", "نادية"), ("Yusuf", "يوسف"), ("Amina", "أمينة"), ("Khalid", "خالد"),
    ("Fatima", "فاطمة"), ("Rashid", "راشد"), ("Huda", "هدى"), ("Tariq", "طارق"), ("Noor", "نور"),
    ("Salim", "سالم"), ("Reem", "ريم"), ("Faisal", "فيصل"), ("Aisha", "عائشة"), ("Hamad", "حمد"),
    ("Mona", "منى"), ("Ali", "علي"), ("Dana", "دانة"), ("Majid", "ماجد"), ("Rania", "رانيا"),
    ("Karim", "كريم"), ("Hind", "هند"), ("Saeed", "سعيد"), ("Lina", "لينا"), ("Adel", "عادل"),
    ("Samira", "سميرة"), ("Nasser", "ناصر"), ("Yasmin", "ياسمين"), ("Ibrahim", "إبراهيم"),
    ("Jamila", "جميلة"), ("Walid", "وليد"), ("Bilal", "بلال"), ("Salma", "سلمى"), ("Fahad", "فهد"),
    ("Priya", "بريا"), ("Ravi", "رافي"), ("Anil", "أنيل"), ("Joseph", "جوزيف"), ("Maria", "ماريا"),
    ("Imran", "عمران"), ("Asif", "آصف"), ("Sunil", "سونيل"), ("Grace", "غريس"), ("Farah", "فرح"),
]

# name patterns (English, Arabic) per sector; {n}/{a} = owner name
SECTORS = {
    "fnb": dict(label="Restaurant & café", label_ar="مطاعم ومقاهي", share=0.16,
                names=[("{n}'s Kitchen", "مطبخ {a}"), ("{n} Café", "مقهى {a}"), ("{n} Grill", "مشويات {a}")],
                rev=(90_000, 0.5), b2b=0.08, cogs=0.38, payroll=0.28, rent=0.11, terms=[30], inv_pm=2,
                dow="retail", season="fnb"),
    "grocery": dict(label="Food supply & grocery", label_ar="توريد مواد غذائية", share=0.12,
                    names=[("{n} Foodstuff Trading", "{a} لتجارة المواد الغذائية"), ("{n} Fresh Supplies", "{a} للتوريدات الطازجة")],
                    rev=(220_000, 0.5), b2b=0.55, cogs=0.72, payroll=0.08, rent=0.04, terms=[30, 30, 45], inv_pm=10,
                    dow="mixed", season="flat"),
    "salon": dict(label="Salon & spa", label_ar="صالونات وسبا", share=0.08,
                  names=[("{n} Beauty Salon", "صالون {a} للتجميل"), ("{n} Spa", "سبا {a}")],
                  rev=(70_000, 0.45), b2b=0.0, cogs=0.15, payroll=0.38, rent=0.13, terms=[30], inv_pm=0,
                  dow="retail", season="salon"),
    "logistics": dict(label="Logistics & delivery", label_ar="خدمات لوجستية وتوصيل", share=0.11,
                      names=[("{n} Logistics", "{a} للخدمات اللوجستية"), ("{n} Delivery Services", "{a} لخدمات التوصيل")],
                      rev=(180_000, 0.55), b2b=0.85, cogs=0.30, payroll=0.36, rent=0.05, terms=[30, 45, 60], inv_pm=6,
                      dow="b2b", season="flat"),
    "construction": dict(label="Construction & fit-out", label_ar="مقاولات وتشطيبات", share=0.10,
                         names=[("{n} Contracting", "{a} للمقاولات"), ("{n} Fit-Out", "{a} للتشطيبات")],
                         rev=(350_000, 0.6), b2b=0.97, cogs=0.45, payroll=0.30, rent=0.03, terms=[60, 60, 90], inv_pm=3,
                         dow="b2b", season="construction"),
    "building": dict(label="Building materials", label_ar="مواد البناء", share=0.08,
                     names=[("{n} Building Materials", "{a} لمواد البناء"), ("{n} Hardware", "{a} للأدوات")],
                     rev=(260_000, 0.5), b2b=0.7, cogs=0.70, payroll=0.08, rent=0.05, terms=[45, 60], inv_pm=8,
                     dow="mixed", season="construction"),
    "it": dict(label="IT & digital services", label_ar="خدمات تقنية ورقمية", share=0.09,
               names=[("{n} Digital", "{a} الرقمية"), ("{n} Tech Solutions", "{a} للحلول التقنية")],
               rev=(140_000, 0.6), b2b=0.95, cogs=0.10, payroll=0.52, rent=0.05, terms=[30, 45], inv_pm=4,
               dow="b2b", season="flat"),
    "retail": dict(label="Retail & fashion", label_ar="تجزئة وأزياء", share=0.12,
                   names=[("{n} Fashion", "{a} للأزياء"), ("{n} Boutique", "بوتيك {a}")],
                   rev=(110_000, 0.5), b2b=0.0, cogs=0.50, payroll=0.18, rent=0.14, terms=[30], inv_pm=0,
                   dow="retail", season="retail"),
    "events": dict(label="Printing & events", label_ar="طباعة وفعاليات", share=0.07,
                   names=[("{n} Printing Press", "مطبعة {a}"), ("{n} Events", "{a} لتنظيم الفعاليات")],
                   rev=(120_000, 0.6), b2b=0.9, cogs=0.40, payroll=0.30, rent=0.06, terms=[30, 45, 60], inv_pm=5,
                   dow="b2b", season="events"),
    "cleaning": dict(label="Cleaning & facilities", label_ar="تنظيف وإدارة مرافق", share=0.07,
                     names=[("{n} Cleaning Services", "{a} لخدمات التنظيف"), ("{n} Facilities Management", "{a} لإدارة المرافق")],
                     rev=(130_000, 0.5), b2b=0.95, cogs=0.12, payroll=0.58, rent=0.04, terms=[30, 45, 60], inv_pm=4,
                     dow="b2b", season="flat"),
}

# who buys from whom inside the network (buyer sector -> supplier sectors)
BUYS_FROM = {
    "fnb": ["grocery", "grocery", "grocery", "cleaning", "events"],
    "grocery": ["logistics", "logistics", "cleaning"],
    "salon": ["retail", "cleaning"],
    "logistics": ["it", "cleaning", "building"],
    "construction": ["building", "building", "building", "logistics", "cleaning", "it"],
    "building": ["logistics", "logistics", "it"],
    "it": ["events", "cleaning"],
    "retail": ["logistics", "logistics", "events", "it"],
    "events": ["logistics", "it", "fnb"],
    "cleaning": ["building", "logistics"],
}

EMIRATES = [("Dubai", "دبي", 0.45), ("Abu Dhabi", "أبوظبي", 0.2), ("Sharjah", "الشارقة", 0.2),
            ("Ajman", "عجمان", 0.08), ("Ras Al Khaimah", "رأس الخيمة", 0.04), ("Fujairah", "الفجيرة", 0.02),
            ("Umm Al Quwain", "أم القيوين", 0.01)]

# external counterparties (outside the network). kind: customer / supplier
EXTERNALS = [
    ("X01", "Government entity A", "customer", 38, 18, 0.06),
    ("X02", "Government entity B", "customer", 30, 15, 0.04),
    ("X03", "Property developer A", "customer", 45, 28, 0.12),
    ("X04", "Property developer B", "customer", 35, 22, 0.08),
    ("X05", "Main contractor A", "customer", 40, 25, 0.10),
    ("X06", "Hotel group A", "customer", 14, 10, 0.02),
    ("X07", "Hotel group B", "customer", 18, 12, 0.03),
    ("X08", "Retail chain A", "customer", 20, 12, 0.03),
    ("X09", "Corporate office park", "customer", 8, 8, 0.01),
    ("X10", "Free-zone company A", "customer", 12, 10, 0.02),
    ("X11", "Free-zone company B", "customer", 22, 15, 0.04),
    ("X12", "School group", "customer", 16, 12, 0.02),
    ("X13", "Hospital group", "customer", 28, 16, 0.05),
    ("X14", "Airline caterer", "customer", 10, 8, 0.01),
    ("X21", "Food importer", "supplier", 0, 0, 0.0),
    ("X22", "Wholesale market", "supplier", 0, 0, 0.0),
    ("X23", "Steel & cement supplier", "supplier", 0, 0, 0.0),
    ("X24", "Beauty products distributor", "supplier", 0, 0, 0.0),
    ("X25", "Garment importer", "supplier", 0, 0, 0.0),
    ("X26", "Fuel & vehicle services", "supplier", 0, 0, 0.0),
    ("X27", "Software & cloud vendor", "supplier", 0, 0, 0.0),
    ("X28", "Paper & print supplier", "supplier", 0, 0, 0.0),
    ("X29", "Chemicals & equipment", "supplier", 0, 0, 0.0),
]
EXT_CUSTOMERS = {
    "fnb": ["X09", "X10"], "grocery": ["X06", "X07", "X14", "X12"], "logistics": ["X08", "X10", "X11", "X03"],
    "construction": ["X01", "X03", "X04", "X05", "X02"], "building": ["X05", "X03", "X04"],
    "it": ["X01", "X02", "X10", "X11", "X13"], "events": ["X01", "X06", "X07", "X09", "X11"],
    "cleaning": ["X09", "X12", "X13", "X06", "X01"], "salon": [], "retail": [],
}
EXT_SUPPLIERS = {
    "fnb": ["X22", "X21"], "grocery": ["X21", "X22"], "salon": ["X24"], "logistics": ["X26"],
    "construction": ["X23"], "building": ["X23"], "it": ["X27"], "retail": ["X25"],
    "events": ["X28"], "cleaning": ["X29"],
}

DOW = {  # Mon..Sun (UAE weekend is Sat-Sun)
    "retail": [0.85, 0.85, 0.9, 0.95, 1.15, 1.35, 1.25],
    "mixed": [1.1, 1.1, 1.1, 1.1, 1.0, 0.8, 0.6],
    "b2b": [1.2, 1.2, 1.2, 1.2, 1.0, 0.25, 0.2],
}


def _season(kind: str, d: date) -> float:
    m = d.month
    ram = any(a <= d <= b for a, b in RAMADAN)
    eid = any(0 <= (d - e).days <= 3 for e in EID)
    f = 1.0
    if kind == "fnb":
        f = {7: 0.72, 8: 0.7, 6: 0.85, 12: 1.15, 1: 1.1}.get(m, 1.0) * (0.85 if ram else 1.0) * (1.4 if eid else 1.0)
    elif kind == "retail":
        f = {1: 1.2, 7: 0.78, 8: 0.75, 11: 1.1, 12: 1.2}.get(m, 1.0) * (1.25 if ram else 1.0) * (1.5 if eid else 1.0)
    elif kind == "salon":
        f = {7: 0.7, 8: 0.7}.get(m, 1.0) * (1.6 if eid else 1.0) * (1.2 if ram else 1.0)
    elif kind == "events":
        f = {6: 0.6, 7: 0.35, 8: 0.35, 9: 0.8, 10: 1.25, 11: 1.35, 12: 1.3, 1: 1.2, 2: 1.2, 3: 1.1}.get(m, 1.0) * (0.6 if ram else 1.0)
    elif kind == "construction":
        f = {7: 0.85, 8: 0.85}.get(m, 1.0) * (0.85 if ram else 1.0)
    return f


def is_ramadan(d: date) -> bool:
    return any(a <= d <= b for a, b in RAMADAN)


def _business_day(d: date, back: bool = False) -> date:
    while d.weekday() >= 5:
        d = d - timedelta(days=1) if back else d + timedelta(days=1)
    return d


@dataclass
class World:
    smes: list[dict]
    externals: list[dict]
    invoices: pd.DataFrame     # all B2B invoices
    flows: pd.DataFrame        # all non-invoice cash flows (sme, date, kind, amount)
    rent: pd.DataFrame         # post-dated rent cheque schedule (known in advance)
    days: pd.DatetimeIndex


def generate(n: int = 240, seed: int = SEED, end: date = TODAY + timedelta(days=75)) -> World:
    """Generate history up to `end` (a little beyond TODAY so replays and 'future' truth exist)."""
    rng = np.random.default_rng(seed)
    days = pd.date_range(START, end, freq="D")
    nd = len(days)
    dlist = [d.date() for d in days]

    # ---- businesses ----------------------------------------------------------
    keys = list(SECTORS)
    shares = np.array([SECTORS[k]["share"] for k in keys])
    counts = np.floor(shares / shares.sum() * n).astype(int)
    counts[np.argmax(shares)] += n - counts.sum()
    sector_of = [k for k, c in zip(keys, counts) for _ in range(c)]
    rng.shuffle(sector_of)
    used = set()
    smes = []
    em_p = np.array([e[2] for e in EMIRATES])
    for i, sec in enumerate(sector_of):
        cfg = SECTORS[sec]
        for _ in range(200):
            fn, fa = FIRST_NAMES[rng.integers(len(FIRST_NAMES))]
            pe, pa = cfg["names"][rng.integers(len(cfg["names"]))]
            name = pe.format(n=fn)
            if name not in used:
                used.add(name)
                break
        em = EMIRATES[rng.choice(len(EMIRATES), p=em_p / em_p.sum())]
        rev = float(cfg["rev"][0] * rng.lognormal(0, cfg["rev"][1]))
        rev = round(min(max(rev, 25_000), 2_500_000), -3)
        pay_day = int(rng.choice([1, 1, 2, 3, 5, 25, 27, 28], p=[.2, .1, .15, .15, .1, .1, .1, .1]))
        k_cheq = int(rng.choice([1, 2, 4, 4, 6, 12], p=[.12, .22, .3, .16, .1, .1]))
        smes.append(dict(
            id=f"S{i + 1:04d}", name=name, name_ar=pa.format(a=fa), owner=fn, owner_ar=fa, sector=sec,
            sector_label=cfg["label"], sector_label_ar=cfg["label_ar"], emirate=em[0], emirate_ar=em[1],
            monthly_revenue=rev, b2b=cfg["b2b"], payroll_day=pay_day, rent_cheques=k_cheq,
            staff=int(max(2, round(rev * cfg["payroll"] / 4_500 * rng.uniform(0.8, 1.2)))),
            # as a payer: mean days late, spread, chance of a very late payment
            pay_mean=float(rng.gamma(2.0, 4.0)), pay_sd=float(rng.uniform(3, 10)),
            pay_very_late=float(rng.choice([0.0, 0.01, 0.03, 0.06], p=[.4, .3, .2, .1])),
            trend=float(rng.normal(0, 0.08)), cover_weeks=float(rng.lognormal(np.log(3.2), 0.5)),
        ))
    by_sec: dict[str, list[int]] = {}
    for idx, s in enumerate(smes):
        by_sec.setdefault(s["sector"], []).append(idx)

    # ---- network links: each business buys from a few network suppliers --------
    for idx, s in enumerate(smes):
        sups = []
        for sec in BUYS_FROM[s["sector"]]:
            pool = [j for j in by_sec.get(sec, []) if j != idx]
            # prefer suppliers in the same emirate
            same = [j for j in pool if smes[j]["emirate"] == s["emirate"]]
            pick_from = same if same and rng.random() < 0.7 else pool
            if pick_from:
                sups.append(int(rng.choice(pick_from)))
        s["network_suppliers"] = sorted(set(sups))
    for s in smes:
        s["network_customers"] = []
    for idx, s in enumerate(smes):
        for j in s["network_suppliers"]:
            smes[j]["network_customers"].append(idx)

    externals = [dict(id=e[0], name=e[1], kind=e[2], pay_mean=e[3], pay_sd=e[4], pay_very_late=e[5]) for e in EXTERNALS]
    ext_by_id = {e["id"]: e for e in externals}

    # ---- daily flows ------------------------------------------------------------
    flow_rows: list[tuple] = []
    inv_rows: list[dict] = []
    rent_rows: list[tuple] = []
    inv_seq = 0
    dow_idx = np.array([d.weekday() for d in dlist])
    season_cache = {k: np.array([_season(k, d) for d in dlist]) for k in {c["season"] for c in SECTORS.values()}}

    def _dow(t: int) -> int:
        return (START + timedelta(days=t)).weekday()

    def payer_delay(p: dict, due: date) -> int:
        late = rng.normal(p["pay_mean"], p["pay_sd"])
        if is_ramadan(due) or due.month in (7, 8):
            late += rng.uniform(2, 8)
        if rng.random() < p["pay_very_late"]:
            late += rng.uniform(35, 90)
        return int(max(-5, round(late)))

    for s in smes:
        cfg = SECTORS[s["sector"]]
        M = s["monthly_revenue"]
        trend = 1 + s["trend"] * np.linspace(0, 1, nd)
        # slow business-level fluctuation (AR(1) on weekly scale)
        ar = np.zeros(nd)
        for t in range(1, nd):
            ar[t] = 0.97 * ar[t - 1] + rng.normal(0, 0.03)
        level = trend * np.exp(ar) * season_cache[cfg["season"]]
        dowf = np.array(DOW[cfg["dow"]])[dow_idx]

        # walk-in / card sales
        walk = (1 - s["b2b"]) * M / 30.4
        if walk > 0:
            sales = walk * level * dowf * rng.lognormal(-0.045, 0.3, nd)
            for t in range(nd):
                flow_rows.append((s["id"], t, "sales", round(float(sales[t]), 2)))
        # small daily running costs on open days
        daily_cost = M * 0.05 / 30.4
        costs = daily_cost * (dowf > 0.3) * rng.uniform(0.7, 1.3, nd) * level
        for t in range(nd):
            if costs[t] > 0:
                flow_rows.append((s["id"], t, "running_costs", -round(float(costs[t]), 2)))

        # B2B invoices issued by this business
        if cfg["inv_pm"] > 0 and s["b2b"] > 0:
            cust_net = s["network_customers"]
            cust_ext = EXT_CUSTOMERS[s["sector"]]
            b2b_month = s["b2b"] * M
            mean_amt = b2b_month / cfg["inv_pm"]
            p_issue = cfg["inv_pm"] / 21.7
            for t in range(-PRE, nd):  # includes pre-history so invoices are already open on day one
                if _dow(t) >= 5 or rng.random() > p_issue:
                    continue
                net_share = min(0.65, 0.18 * len(cust_net)) if cust_net else 0.0
                if cust_net and (not cust_ext or rng.random() < net_share):
                    buyer = smes[int(rng.choice(cust_net))]
                    buyer_id, payer = buyer["id"], buyer
                    amt = mean_amt * rng.lognormal(-0.5, 0.45) * level[max(t, 0)]
                else:
                    if not cust_ext:
                        continue
                    xid = str(rng.choice(cust_ext))
                    buyer_id, payer = xid, ext_by_id[xid]
                    amt = mean_amt * rng.lognormal(0.05, 0.45) * level[max(t, 0)]
                terms = int(rng.choice(cfg["terms"]))
                issue = START + timedelta(days=t)
                due = issue + timedelta(days=terms)
                paid = _business_day(due + timedelta(days=payer_delay(payer, due)))
                inv_seq += 1
                inv_rows.append(dict(invoice_id=f"INV{inv_seq:06d}", payee=s["id"], payer=buyer_id,
                                     issue=issue, due=due, paid=paid, amount=round(float(amt), -1), terms=terms))

        # purchases from external suppliers (the business pays)
        purch_month = cfg["cogs"] * M
        net_sup = s["network_suppliers"]
        # network suppliers invoice this business through their own loop (above); here only the external part
        ext_sups = EXT_SUPPLIERS[s["sector"]]
        ext_share = 0.55 if net_sup else 1.0
        n_bills = 4 if M > 100_000 else 2
        for t in range(-PRE, nd):  # includes pre-history so invoices are already open on day one
            if _dow(t) >= 5 or rng.random() > n_bills / 21.7:
                continue
            amt = purch_month * ext_share / n_bills * rng.lognormal(-0.05, 0.3) * level[max(t, 0)]
            xid = str(rng.choice(ext_sups))
            issue = START + timedelta(days=t)
            terms = int(rng.choice([15, 30, 30, 45]))
            due = issue + timedelta(days=terms)
            paid = _business_day(due + timedelta(days=int(max(-3, round(rng.normal(s["pay_mean"] * 0.5, 3))))))
            inv_seq += 1
            inv_rows.append(dict(invoice_id=f"INV{inv_seq:06d}", payee=xid, payer=s["id"], issue=issue, due=due,
                                 paid=paid, amount=round(float(amt), -1), terms=terms))

        # WPS payroll (monthly, moved to the previous working day if on a weekend)
        payroll = M * cfg["payroll"] * rng.uniform(0.9, 1.1)
        for y, m in sorted({(d.year, d.month) for d in dlist}):
            try:
                pd_ = date(y, m, s["payroll_day"])
            except ValueError:
                continue
            pd_ = _business_day(pd_, back=True)
            if START <= pd_ <= end:
                t = (pd_ - START).days
                flow_rows.append((s["id"], t, "payroll", -round(float(payroll * (1 + s["trend"] * t / nd)), -2)))

        # rent: annual contract paid by post-dated cheques
        annual_rent = 12 * M * cfg["rent"] * rng.uniform(0.8, 1.2)
        start_m = int(rng.integers(1, 13))
        k = s["rent_cheques"]
        cheque = round(annual_rent / k, -2)
        for y in (2024, 2025, 2026, 2027):
            for i in range(k):
                mm = start_m + i * (12 // k)
                yy = y + (mm - 1) // 12
                mm = (mm - 1) % 12 + 1
                cd = date(yy, mm, 1)
                if START <= cd <= end:
                    rent_rows.append((s["id"], cd, float(cheque)))
                    flow_rows.append((s["id"], (cd - START).days, "rent_cheque", -float(cheque)))

        # utilities (DEWA / ADDC / SEWA...)
        util = M * 0.018
        uday = int(rng.integers(8, 16))
        for y, m in sorted({(d.year, d.month) for d in dlist}):
            ud = date(y, m, uday)
            if START <= ud <= end:
                t = (ud - START).days
                flow_rows.append((s["id"], t, "utilities", -round(float(util * season_cache["flat"][t] * rng.uniform(0.8, 1.3) * (1.35 if m in (6, 7, 8, 9) else 1.0)), -1)))

    invoices = pd.DataFrame(inv_rows)
    for c in ("issue", "due", "paid"):
        invoices[c] = pd.to_datetime(invoices[c])

    # a business buys from network suppliers in proportion to its own size: cap each buyer's monthly network
    # purchases at 60% of its cost-of-goods budget (suppliers' sales shrink accordingly; calibration below
    # then keeps everyone's margin realistic)
    net = invoices.payee.str.startswith("S") & invoices.payer.str.startswith("S")
    months_all = (nd + PRE) / 30.4
    per_buyer = invoices[net].groupby("payer").amount.sum() / months_all
    cap = pd.Series({s["id"]: 0.6 * SECTORS[s["sector"]]["cogs"] * s["monthly_revenue"] for s in smes})
    factor = (cap / per_buyer).clip(upper=1.0).fillna(1.0)
    invoices.loc[net, "amount"] = (invoices.loc[net, "amount"] * invoices.loc[net, "payer"].map(factor)).round(-1)
    invoices = invoices[invoices.amount >= 100].reset_index(drop=True)
    flows = pd.DataFrame(flow_rows, columns=["sme", "t", "kind", "amount"])

    # VAT: 5% of (sales + invoiced revenue - purchases) per calendar quarter, due on the 28th after quarter end
    flows_sales = flows[flows.kind == "sales"].groupby(["sme", "t"]).amount.sum()
    vat_rows = []
    qdays = pd.Series(days).dt.to_period("Q").values
    for s in smes:
        sid = s["id"]
        sal = flows_sales.get(sid, pd.Series(dtype=float))
        sal_q = pd.Series(sal.values, index=qdays[sal.index.values]).groupby(level=0).sum() if len(sal) else pd.Series(dtype=float)
        rev_inv = invoices[invoices.payee == sid]
        rev_q = rev_inv.groupby(rev_inv.issue.dt.to_period("Q")).amount.sum()
        pur_inv = invoices[invoices.payer == sid]
        pur_q = pur_inv.groupby(pur_inv.issue.dt.to_period("Q")).amount.sum()
        for q in sorted(set(qdays)):
            due = (q.end_time + pd.Timedelta(days=28)).date()
            if due > end or due < START:
                continue
            base = sal_q.get(q, 0.0) + rev_q.get(q, 0.0) - pur_q.get(q, 0.0)
            vat = max(0.0, 0.05 * base)
            if vat > 0:
                vat_rows.append((sid, (due - START).days, "vat", -round(float(vat), -1)))
    flows = pd.concat([flows, pd.DataFrame(vat_rows, columns=flows.columns)], ignore_index=True)

    # ---- calibrate: profitable businesses whose problem is timing, not losses ----------------
    # Target retained cash ~1-2% of revenue; the rest of the profit leaves as monthly owner drawings, a shortfall in
    # margin is closed by trimming external purchases, then payroll/running costs.
    months = nd / 30.4
    by_kind = flows.groupby(["sme", "kind"]).amount.sum()
    # cash basis: only invoices actually settled inside the simulated window count
    inwin = (invoices.paid >= pd.Timestamp(START)) & (invoices.paid <= pd.Timestamp(end))
    rev_in = invoices[inwin].groupby("payee").amount.sum()
    pay_net = invoices[inwin & invoices.payee.str.startswith("S")].groupby("payer").amount.sum()
    ext_mask = invoices.payee.str.startswith("X")
    pay_ext = invoices[inwin & ext_mask].groupby("payer").amount.sum()
    draw_rows = []
    for s in smes:
        sid = s["id"]
        k = by_kind.get(sid, pd.Series(dtype=float))
        revenue = float(k.get("sales", 0.0) + rev_in.get(sid, 0.0))
        costs = float(-k.drop("sales", errors="ignore").sum() + pay_net.get(sid, 0.0) + pay_ext.get(sid, 0.0))  # incl. VAT
        target = float(np.clip(rng.normal(0.015, 0.012), -0.004, 0.045)) * revenue
        gap = revenue - costs - target
        s["margin_target"] = round(target / revenue, 3) if revenue else 0.0
        if gap > 0:
            draw = gap / months
            dday = int(rng.integers(18, 24))
            for y, m in sorted({(d.year, d.month) for d in dlist}):
                dd = date(y, m, dday)
                if START <= dd <= end:
                    draw_rows.append((sid, (dd - START).days, "owner_drawings", -round(draw, -2)))
        else:
            need = -gap
            ext_amt = float(pay_ext.get(sid, 0.0))
            cut = min(need / 0.95, 0.85 * ext_amt)  # cheaper purchases also raise VAT a little
            if cut > 0:
                f_ = 1 - cut / ext_amt
                sel = ext_mask & (invoices.payer == sid)
                invoices.loc[sel, "amount"] = (invoices.loc[sel, "amount"] * f_).round(-1)
                need -= cut * 0.95
            if need > 0:
                sel = (flows.sme == sid) & flows.kind.isin(["payroll", "running_costs"])
                tot = -flows.loc[sel, "amount"].sum()
                if tot > 0:
                    flows.loc[sel, "amount"] *= max(0.3, 1 - need / tot)
    flows = pd.concat([flows, pd.DataFrame(draw_rows, columns=flows.columns)], ignore_index=True)

    # opening cash: a few weeks of outflows (fragile businesses hold very little)
    out_month = flows[(flows.amount < 0) & (flows.t < 90)].groupby("sme").amount.sum().abs() / 3
    pay_month = invoices[(invoices.issue < pd.Timestamp(START) + pd.Timedelta(days=90))].groupby("payer").amount.sum() / 3
    for s in smes:
        monthly_out = float(out_month.get(s["id"], 0) + pay_month.get(s["id"], 0))
        s["opening_cash"] = round(monthly_out / 4.33 * s["cover_weeks"] + s["monthly_revenue"] * 0.15, -3)
        s["network_suppliers"] = [smes[j]["id"] for j in s["network_suppliers"]]
        s["network_customers"] = sorted({smes[j]["id"] for j in s["network_customers"]})

    rent = pd.DataFrame(rent_rows, columns=["sme", "date", "amount"])
    rent["date"] = pd.to_datetime(rent["date"])
    return World(smes=smes, externals=externals, invoices=invoices, flows=flows, rent=rent, days=days)


def save(world: World) -> None:
    ARTIFACTS.mkdir(parents=True, exist_ok=True)
    (ARTIFACTS / "smes.json").write_text(json.dumps(world.smes, ensure_ascii=False, indent=1), encoding="utf-8")
    (ARTIFACTS / "externals.json").write_text(json.dumps(world.externals, indent=1), encoding="utf-8")
    world.invoices.to_pickle(ARTIFACTS / "invoices.pkl")
    world.flows.to_pickle(ARTIFACTS / "flows.pkl")
    world.rent.to_pickle(ARTIFACTS / "rent.pkl")
    pd.Series(world.days).to_pickle(ARTIFACTS / "days.pkl")


def load() -> World:
    smes = json.loads((ARTIFACTS / "smes.json").read_text(encoding="utf-8"))
    externals = json.loads((ARTIFACTS / "externals.json").read_text(encoding="utf-8"))
    return World(smes=smes, externals=externals, invoices=pd.read_pickle(ARTIFACTS / "invoices.pkl"),
                 flows=pd.read_pickle(ARTIFACTS / "flows.pkl"), rent=pd.read_pickle(ARTIFACTS / "rent.pkl"),
                 days=pd.DatetimeIndex(pd.read_pickle(ARTIFACTS / "days.pkl")))


def ensure() -> World:
    if not (ARTIFACTS / "smes.json").exists():
        save(generate())
    return load()
