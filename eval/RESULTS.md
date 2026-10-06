# Sila — evaluation results

All data is synthetic (240 UAE SMEs, Jan 2025 – Sep 2026). Models are trained on data up to 31 Mar 2026 and
calibrated on Jan–Mar 2026. **Everything below is scored on Apr–Sep 2026, which the models never saw.**
Reproduce with `python -m scripts.build && python -m eval.run_eval`.

## 1. Early warning — will this business run out of cash in the next 28 days?

5,075 business-weeks (22 weekly origins); 3.1% of them ran short.

| | ROC-AUC | PR-AUC | Precision | Recall |
|---|---|---|---|---|
| **Sila forecast** (alert at P ≥ 0.3) | **0.988** | **0.848** | **76%** | **71%** |
| "Days of cash cover" rule, same number of alerts | 0.955 | 0.502 | 53% | 49% |

Of 44 shortfalls that started in the window, Sila warned before **98%** of them
(**91% at least 7 days ahead**); median warning **25 days** before the
first day short. Brier score 0.0119.

## 2. Calibration

Real balances fell inside the P10–P90 band **78.6%** of the time (target 80%), after split-conformal
calibration on Jan–Mar 2026.

## 3. When will this invoice actually be paid?

62,327 open invoices scored. LightGBM quantile model: MAE **8.48 days** vs
8.66 days for "due date + payer's average delay" (**2% lower**).
P10–P90 range contains the real payment day 81% of the time.

## 4. Daily sales, 28 days ahead

WAPE **25.9%** vs 31.0% for a same-weekday 4-week average (**16% lower**).

## 5. Prevention — six-month replay

Sila ran every morning from 2026-04-01 to 2026-09-27 on the live ledger; each owner accepted a
suggestion with 80% probability.

| | Result |
|---|---|
| Shortfalls fully prevented | **22 of 52 (42%)** |
| Days short avoided (those shortfalls) | **55%** |
| All shortfall days, incl. 9 businesses already short on day one | −46% |
| Moves accepted | 397 (217 early payment, 174 grace, 6 chain) |
| Cash moved inside the network | AED 5,417,924 (median move AED 9,670) |
| Businesses helped / helpers | 36 / 100 |
| **Helpers pushed into a shortfall** | **0** |
| New debt created | 0 |
| Early-payment discounts paid | AED 22,439 vs AED 44,821 for the same cover as a 12% APR loan (**50% cheaper**) |

What the network cannot fix: businesses with no trading partners inside the network, and gaps too large for partners
to cover safely. For those Sila gives the early warning and recommends talking to the bank before the crunch.
