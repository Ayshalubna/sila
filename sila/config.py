"""Shared constants: calendar, horizons and safety settings."""
from __future__ import annotations

import os
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ARTIFACTS = Path(os.getenv("SILA_ARTIFACTS", ROOT / "artifacts"))

START = date(2025, 1, 1)          # first day of synthetic history
TODAY = date(2026, 9, 28)         # "today" in the demo; data ends here
TRAIN_END = date(2026, 3, 31)     # models are trained on data up to here
REPLAY_START = date(2026, 4, 1)   # 6-month out-of-sample replay (Apr-Sep 2026)

HORIZON = 28                      # forecast / alert horizon in days
MIN_LEAD = 7                      # an alert only counts if raised at least this many days early
N_PATHS = 120                     # Monte-Carlo paths per business

# Ramadan / Eid (approximate) - used as calendar features, not as labels
RAMADAN = [(date(2025, 3, 1), date(2025, 3, 30)), (date(2026, 2, 18), date(2026, 3, 19))]
EID = [date(2025, 3, 30), date(2025, 6, 6), date(2026, 3, 20), date(2026, 5, 27)]

# Mesh safety settings
PAYER_BUFFER_DAYS = 10            # a payer must keep >= this many days of its own outflows after helping
MAX_MOVE_SHARE = 0.6              # a single move may use at most this share of a payer's spare cash
MIN_MOVE = 1_000                  # AED; smaller moves are not worth the owner's attention
EARLY_PAY_RATE_30D = 0.006        # 0.6% discount for paying 30 days early (pro-rata), paid by the receiver
GRACE_DAYS = 30                   # length of a no-fee grace period on a network invoice
ACCEPT_RATE = 0.8                 # share of suggested moves owners accept in the replay
ILLUSTRATIVE_LOAN_APR = 0.12      # assumption used only to compare cost with short-term borrowing
