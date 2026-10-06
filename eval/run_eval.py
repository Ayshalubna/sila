"""Evaluation harness and CI regression gate.

Everything is scored on the six months the models never saw (Apr-Sep 2026):

1. Early warning   - P(shortfall within 28 days) vs a "days of cash cover" rule
2. Calibration     - share of real balances inside the P10-P90 band
3. Payment timing  - days until an open invoice is paid vs "due date + payer's average delay"
4. Sales           - 28-day daily sales vs a same-weekday average of the last 4 weeks
5. Prevention      - the 6-month replay of Sila's moves (see sila/replay.py)

    python -m eval.run_eval            # writes eval/results.json and eval/RESULTS.md, fails if below floors
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
from sklearn.metrics import average_precision_score, roc_auc_score

from sila import forecast, ledger, synth
from sila.config import ARTIFACTS, HORIZON, MIN_LEAD, REPLAY_START, TODAY
from sila.ledger import day_index, shortfall_episodes
from sila.mesh import ALERT_P

OUT = Path(__file__).resolve().parent

THRESHOLDS = {
    "alerts.auc": 0.95, "alerts.pr_auc": 0.70, "alerts.recall": 0.65, "alerts.precision": 0.60,
    "calibration.coverage_p10_p90": 0.74, "timing.mae_improvement": 0.0, "timing.coverage_p10_p90": 0.72, "sales.wape_improvement": 0.05,
    "replay.episodes_prevented_share": 0.35, "replay.episode_days_avoided_share": 0.35,
    "replay.saving_vs_loan": 0.4,
}
MAX = {"replay.helpers_pushed_into_shortfall": 0, "calibration.coverage_p10_p90_max": 0.88}


def evaluate(F: forecast.Forecaster) -> dict:
    L = F.led
    r0, t_end = day_index(REPLAY_START), day_index(TODAY)
    weekly = list(range(r0, t_end - HORIZON + 1, 7))

    # ---- 1-2: alerts and calibration (weekly origins) ----
    P, Y, NAIVE, cov = [], [], [], []
    for t in weekly:
        fc = F.forecast(t)
        ok = L.balance[:, t] >= 0
        fut = L.balance[:, t + 1:t + HORIZON + 1]
        y = (fut < 0).any(axis=1)
        P += list(fc.p_short[ok])
        Y += list(y[ok])
        flows = L.base[:, t - 27:t + 1] + L.inv_flow[:, t - 27:t + 1]
        out = -np.minimum(flows, 0).sum(axis=1) / 28
        NAIVE += list((-(L.balance[:, t] / np.maximum(out, 1)))[ok])
        cov.append(((fut >= fc.q10) & (fut <= fc.q90)).mean())
    P, Y, NAIVE = np.array(P), np.array(Y), np.array(NAIVE)
    a = P >= ALERT_P
    # the rule with the same number of alerts, for a like-for-like comparison
    k = int(a.sum())
    naive_alert = np.zeros_like(Y)
    naive_alert[np.argsort(-NAIVE)[:k]] = True

    # ---- lead time: daily forecasts before each shortfall that starts in the window ----
    start_neg = L.balance[:, r0 - 1] < 0
    eps = [e for e in shortfall_episodes(L.balance, r0 + HORIZON, t_end) if not start_neg[e[0]]]
    first_alert: dict[tuple, int] = {}
    pending = {(i, st) for i, st, _ in eps}
    for t in range(r0, t_end):
        if not pending:
            break
        fc = F.forecast(t)
        for i, st in list(pending):
            if st - HORIZON <= t < st and fc.p_short[i] >= ALERT_P and L.balance[i, t] >= 0:
                first_alert[(i, st)] = st - t
                pending.discard((i, st))
    leads = list(first_alert.values())

    # ---- 3: payment timing (open invoices at weekly origins) ----
    err_m, err_b, inside = [], [], []
    for t in weekly:
        op = L.open_invoices(t)
        op = op[(op.t_settle <= t + 120)]
        if op.empty:
            continue
        q = F.predict_delay(op, t)
        actual = (op.t_settle.values - t).astype(float)
        base_pred = F.baseline_delay(op, np.full(len(op), t))
        err_m += list(np.abs(q[:, 1] - actual))
        err_b += list(np.abs(base_pred - actual))
        inside += list((actual >= q[:, 0] - 0.5) & (actual <= q[:, 2] + 0.5))
    mae_m, mae_b = float(np.mean(err_m)), float(np.mean(err_b))

    # ---- 4: sales (weekly origins, 28 days ahead) ----
    S = F.kind_mats["sales"]
    rows = F.sales_rows
    num_m = num_b = den = 0.0
    for t in weekly:
        pred = F.predict_sales(t)[rows, :, 1]
        act = S[rows, t + 1:t + HORIZON + 1]
        dm = F.sales.dow_mean(t, weeks=4)[rows]
        dows = (np.arange(t + 1, t + HORIZON + 1) + forecast.START.weekday()) % 7
        naive = dm[:, dows]
        num_m += np.abs(pred - act).sum()
        num_b += np.abs(naive - act).sum()
        den += act.sum()
    wape_m, wape_b = num_m / den, num_b / den

    replay = json.loads((ARTIFACTS / "replay_metrics.json").read_text())
    return {
        "alerts": {
            "origins": len(weekly), "business_weeks": int(len(Y)), "base_rate": round(float(Y.mean()), 3),
            "threshold": ALERT_P, "auc": round(roc_auc_score(Y, P), 3), "pr_auc": round(average_precision_score(Y, P), 3),
            "precision": round(float(Y[a].mean()), 3), "recall": round(float(a[Y].mean()), 3), "alerts": int(a.sum()),
            "naive_auc": round(roc_auc_score(Y, NAIVE), 3), "naive_pr_auc": round(average_precision_score(Y, NAIVE), 3),
            "naive_precision": round(float(Y[naive_alert].mean()), 3), "naive_recall": round(float(naive_alert[Y].mean()), 3),
            "brier": round(float(np.mean((P - Y) ** 2)), 4),
            "shortfalls_scored": len(eps), "warned": len(leads),
            "warned_share": round(len(leads) / max(len(eps), 1), 3),
            "warned_7d_share": round(sum(x >= MIN_LEAD for x in leads) / max(len(eps), 1), 3),
            "median_lead_days": float(np.median(leads)) if leads else 0.0,
        },
        "calibration": {"coverage_p10_p90": round(float(np.mean(cov)), 3), "target": 0.8,
                        "spread": [round(float(x), 2) for x in (F.spread if F.spread is not None else [])]},
        "timing": {"invoices_scored": len(err_m), "mae_days": round(mae_m, 2), "baseline_mae_days": round(mae_b, 2),
                   "mae_improvement": round(1 - mae_m / mae_b, 3), "coverage_p10_p90": round(float(np.mean(inside)), 3)},
        "sales": {"wape": round(float(wape_m), 3), "baseline_wape": round(float(wape_b), 3),
                  "wape_improvement": round(float(1 - wape_m / wape_b), 3)},
        "replay": replay,
    }


def gate(res: dict) -> list[str]:
    fails = []
    for key, floor in THRESHOLDS.items():
        sec, k = key.split(".")
        if res[sec][k] < floor:
            fails.append(f"{key} = {res[sec][k]} < {floor}")
    if res["replay"]["helpers_pushed_into_shortfall"] > MAX["replay.helpers_pushed_into_shortfall"]:
        fails.append("a helper was pushed into a shortfall")
    if res["calibration"]["coverage_p10_p90"] > MAX["calibration.coverage_p10_p90_max"]:
        fails.append("P10-P90 band is too wide")
    return fails


def report(r: dict) -> str:
    a, c, tm, s, rp = r["alerts"], r["calibration"], r["timing"], r["sales"], r["replay"]
    return f"""# Sila — evaluation results

All data is synthetic (240 UAE SMEs, Jan 2025 – Sep 2026). Models are trained on data up to 31 Mar 2026 and
calibrated on Jan–Mar 2026. **Everything below is scored on Apr–Sep 2026, which the models never saw.**
Reproduce with `python -m scripts.build && python -m eval.run_eval`.

## 1. Early warning — will this business run out of cash in the next 28 days?

{a['business_weeks']:,} business-weeks ({a['origins']} weekly origins); {a['base_rate']:.1%} of them ran short.

| | ROC-AUC | PR-AUC | Precision | Recall |
|---|---|---|---|---|
| **Sila forecast** (alert at P ≥ {a['threshold']}) | **{a['auc']}** | **{a['pr_auc']}** | **{a['precision']:.0%}** | **{a['recall']:.0%}** |
| "Days of cash cover" rule, same number of alerts | {a['naive_auc']} | {a['naive_pr_auc']} | {a['naive_precision']:.0%} | {a['naive_recall']:.0%} |

Of {a['shortfalls_scored']} shortfalls that started in the window, Sila warned before **{a['warned_share']:.0%}** of them
(**{a['warned_7d_share']:.0%} at least 7 days ahead**); median warning **{a['median_lead_days']:.0f} days** before the
first day short. Brier score {a['brier']}.

## 2. Calibration

Real balances fell inside the P10–P90 band **{c['coverage_p10_p90']:.1%}** of the time (target 80%), after split-conformal
calibration on Jan–Mar 2026.

## 3. When will this invoice actually be paid?

{tm['invoices_scored']:,} open invoices scored. LightGBM quantile model: MAE **{tm['mae_days']} days** vs
{tm['baseline_mae_days']} days for "due date + payer's average delay" (**{tm['mae_improvement']:.0%} lower**).
P10–P90 range contains the real payment day {tm['coverage_p10_p90']:.0%} of the time.

## 4. Daily sales, 28 days ahead

WAPE **{s['wape']:.1%}** vs {s['baseline_wape']:.1%} for a same-weekday 4-week average (**{s['wape_improvement']:.0%} lower**).

## 5. Prevention — six-month replay

Sila ran every morning from {rp['window'][0]} to {rp['window'][1]} on the live ledger; each owner accepted a
suggestion with 80% probability.

| | Result |
|---|---|
| Shortfalls fully prevented | **{rp['episodes_prevented']} of {rp['episodes_baseline']} ({rp['episodes_prevented_share']:.0%})** |
| Days short avoided (those shortfalls) | **{rp['episode_days_avoided_share']:.0%}** |
| All shortfall days, incl. {rp['already_short_at_start']} businesses already short on day one | −{rp['shortfall_days_reduction']:.0%} |
| Moves accepted | {rp['moves_accepted']} ({', '.join(f"{v} {k.replace('_', ' ')}" for k, v in rp['moves_by_kind'].items())}) |
| Cash moved inside the network | AED {rp['aed_moved']:,} (median move AED {rp['median_move']:,}) |
| Businesses helped / helpers | {rp['businesses_helped']} / {rp['helpers']} |
| **Helpers pushed into a shortfall** | **{rp['helpers_pushed_into_shortfall']}** |
| New debt created | {rp['new_debt_created']} |
| Early-payment discounts paid | AED {rp['fees_paid']:,} vs AED {rp['loan_cost_equivalent']:,} for the same cover as a 12% APR loan (**{rp['saving_vs_loan']:.0%} cheaper**) |

What the network cannot fix: businesses with no trading partners inside the network, and gaps too large for partners
to cover safely. For those Sila gives the early warning and recommends talking to the bank before the crunch.
"""


def main() -> int:
    world = synth.ensure()
    F = forecast.Forecaster(ledger.Ledger.build(world)).load()
    res = evaluate(F)
    res["thresholds"] = THRESHOLDS
    (OUT / "results.json").write_text(json.dumps(res, indent=1, default=float))
    (OUT / "RESULTS.md").write_text(report(res))
    print(report(res))
    fails = gate(res)
    if fails:
        print("REGRESSION:\n  " + "\n  ".join(fails))
        return 1
    print("all evaluation gates passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
