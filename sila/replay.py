"""Replay: run Sila every morning over six months it never saw in training (Apr-Sep 2026).

Each day Sila forecasts every business from the *current* ledger, proposes moves, re-forecasts to
verify them, and each owner accepts with probability ACCEPT_RATE. Accepted moves change settlement
dates in the ledger, so later days see their effect. The baseline is the same ledger with no Sila.
Decisions only use forecasts; the actual future is only used to score the outcome.
"""
from __future__ import annotations

import json
import time
from collections import Counter

import numpy as np

from .config import ACCEPT_RATE, ARTIFACTS, REPLAY_START, TODAY
from .forecast import Forecaster
from .ledger import Ledger, day_index, shortfall_episodes, to_date
from .mesh import Mesh


def run(F: Forecaster, start=REPLAY_START, end=TODAY, accept_rate: float = ACCEPT_RATE, seed: int = 11,
        step: int = 1, verbose: bool = False, mesh: Mesh | None = None) -> dict:
    base: Ledger = F.led
    state = base.copy()
    mesh = mesh or Mesh(F)
    rng = np.random.default_rng(seed)
    t0, t1 = day_index(start), day_index(end)
    log = []
    tic = time.time()
    for t in range(t0, t1, step):
        fc = F.forecast(t, ledger=state)
        props = mesh.propose(fc, ledger=state)
        if not props:
            continue
        props, _ = mesh.verify(t, state, props, fc)
        accepted = [m for m in props if rng.random() < accept_rate]
        for m in props:
            m.status = "accepted" if m in accepted else "declined"
            d = m.to_dict()
            d["date"] = to_date(t).isoformat()
            log.append(d)
        Mesh.apply(state, accepted, t)
        if verbose and t % 14 == 0:
            print(to_date(t), len(log), round(time.time() - tic, 1))
    return dict(state=state, log=log, t0=t0, t1=t1)


def score(base: Ledger, state: Ledger, log: list[dict], t0: int, t1: int) -> dict:
    ids = base.ids
    b_neg = (base.balance[:, t0:t1] < 0)
    s_neg = (state.balance[:, t0:t1] < 0)
    b_days, s_days = b_neg.sum(1), s_neg.sum(1)
    b_eps = shortfall_episodes(base.balance, t0, t1)
    s_eps = shortfall_episodes(state.balance, t0, t1)
    # businesses already short on day one cannot be "prevented" - report them separately
    start_neg = base.balance[:, t0 - 1] < 0
    acc = [m for m in log if m["status"] == "accepted"]
    helpers = {m["helper"] for m in acc} | {leg["payer"] for m in acc for leg in m["legs"]} | \
        {leg["payee"] for m in acc for leg in m["legs"]}
    helped = {m["helps"] for m in acc}
    only_helpers = [base.idx[h] for h in helpers - helped]
    harmed = [ids[i] for i in only_helpers if s_days[i] > b_days[i]]
    moved = sum(m["amount"] for m in acc)
    fees = sum(m["fee"] for m in acc)
    loan = sum(m["loan_cost"] for m in acc)
    # each baseline shortfall, scored on its own days: fully prevented, or how many of its days were avoided
    eps_prev = []
    for i, st, _depth in b_eps:
        if start_neg[i]:
            continue
        en = st
        while en < base.balance.shape[1] and base.balance[i, en] < 0:
            en += 1
        eps_prev.append((i, st, en))
    prevented = [e for e in eps_prev if (state.balance[e[0], e[1]:e[2]] >= 0).all()]
    ep_days = sum(e[2] - e[1] for e in eps_prev)
    ep_days_after = sum(int((state.balance[e[0], e[1]:e[2]] < 0).sum()) for e in eps_prev)
    new_eps = [e for e in s_eps if not start_neg[e[0]] and not (base.balance[e[0], e[1]] < 0)]
    biz_b = {e[0] for e in eps_prev}
    biz_s = {i for i in range(len(ids)) if not start_neg[i] and s_neg[i].any()}
    return {
        "window": [to_date(t0).isoformat(), to_date(t1 - 1).isoformat()],
        "businesses": len(ids),
        "shortfall_days_baseline": int(b_days.sum()), "shortfall_days_sila": int(s_days.sum()),
        "shortfall_days_reduction": round(1 - s_days.sum() / max(b_days.sum(), 1), 3),
        "episodes_baseline": len(eps_prev), "episodes_prevented": len(prevented),
        "episodes_prevented_share": round(len(prevented) / max(len(eps_prev), 1), 3),
        "episode_days_avoided_share": round(1 - ep_days_after / max(ep_days, 1), 3),
        "new_episodes_created": len(new_eps),
        "businesses_short_baseline": len(biz_b), "businesses_short_sila": len(biz_s),
        "already_short_at_start": int(start_neg.sum()),
        "moves_proposed": len(log), "moves_accepted": len(acc),
        "moves_by_kind": dict(Counter(m["kind"] for m in acc)),
        "businesses_helped": len(helped), "helpers": len(helpers - helped),
        "helpers_pushed_into_shortfall": len(harmed),
        "aed_moved": round(moved), "fees_paid": round(fees), "loan_cost_equivalent": round(loan),
        "saving_vs_loan": round(1 - fees / max(loan, 1), 3),
        "median_move": round(float(np.median([m["amount"] for m in acc])) if acc else 0),
        "new_debt_created": 0,
    }


def save(result: dict, metrics: dict) -> None:
    ARTIFACTS.mkdir(parents=True, exist_ok=True)
    (ARTIFACTS / "replay_log.json").write_text(json.dumps(result["log"], indent=0))
    (ARTIFACTS / "replay_metrics.json").write_text(json.dumps(metrics, indent=1))
    state: Ledger = result["state"]
    np.save(ARTIFACTS / "replay_balance.npy", state.balance.astype(np.float32))
