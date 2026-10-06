"""REST API + web app.

Run:  python -m scripts.serve            (or: uvicorn sila.api:api)
Docs: http://localhost:8000/docs

Visitors are identified by an anonymous random session id (header X-Sila-Session) so their decisions
on suggested moves stay in their own sandbox.
"""
from __future__ import annotations

import os
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Header, HTTPException, Query
from fastapi import Path as P
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from . import service
from .hardening import AccessLog, RateLimit, SecurityHeaders, warm_up

BUSINESS_ID = r"^S\d{4}$"
MOVE_ID = r"^M\d{4}-\d{2}$"
SESSION_ID = r"^[A-Za-z0-9]{8,40}$"
PARTY_ID = r"^(\*|S\d{4}|X\d{2})$"


@asynccontextmanager
async def lifespan(_app):
    if os.getenv("SILA_WARMUP", "1") == "1":
        warm_up()
    yield


api = FastAPI(title="Sila — SME Liquidity Mesh", version="1.0.0", lifespan=lifespan,
              description="Predicts small-business cash shortfalls weeks ahead and moves the network's own money "
                          "to prevent them - no loans, no interest, nothing without both owners' consent.")
api.add_middleware(GZipMiddleware, minimum_size=1000)
api.add_middleware(SecurityHeaders)
api.add_middleware(RateLimit, reads_per_min=int(os.getenv("SILA_READS_PER_MIN", "300")),
                   writes_per_min=int(os.getenv("SILA_WRITES_PER_MIN", "40")))
api.add_middleware(AccessLog)


def S() -> service.Sila:
    return service.get()


def _sid(x_sila_session: str | None) -> str | None:
    if x_sila_session is None:
        return None
    import re
    if not re.fullmatch(SESSION_ID, x_sila_session):
        raise HTTPException(422, "invalid session id")
    return x_sila_session


class Decision(BaseModel):
    party: str = Field(pattern="^(helped|helper)$", description="which owner is answering")
    decision: str = Field(pattern="^(accept|decline)$")


class WhatIf(BaseModel):
    business: str = Field(pattern=BUSINESS_ID, examples=["S0050"])
    sales_change: float = Field(0.0, ge=-0.9, le=1.0, description="e.g. -0.2 = sales 20% lower")
    late_days: int = Field(0, ge=0, le=120, description="customers pay this many days later than expected")
    late_payer: str = Field("*", pattern=PARTY_ID, description="'*' for all customers or one customer id")
    expense: float = Field(0.0, ge=0, le=5_000_000, description="one-off extra payment (AED)")
    expense_day: int = Field(7, ge=1, le=28)


@api.get("/health")
def health():
    s = S()
    return {"status": "ok", "today": s.overview()["today"], "businesses": len(s.ids), "boot_seconds": s.boot_seconds}


@api.get("/api/overview")
def overview(x_sila_session: str | None = Header(None)):
    return S().overview(_sid(x_sila_session))


@api.get("/api/businesses")
def businesses(q: str = Query("", max_length=60), sector: str = Query("", pattern=r"^[a-z]{0,20}$"),
               emirate: str = Query("", max_length=30), status: str = Query("", pattern=r"^(|safe|watch|at_risk|short)$"),
               sort: str = Query("risk", pattern=r"^(risk|name|balance|revenue)$"), page: int = Query(1, ge=1, le=100),
               size: int = Query(25, ge=1, le=100), x_sila_session: str | None = Header(None)):
    return S().businesses(_sid(x_sila_session), q, sector, emirate, status, sort, page, size)


@api.get("/api/businesses/{business_id}")
def business(business_id: str = P(..., pattern=BUSINESS_ID), x_sila_session: str | None = Header(None)):
    if business_id not in S().idx:
        raise HTTPException(404, "business not found")
    return S().business(business_id, _sid(x_sila_session))


@api.get("/api/network")
def network(x_sila_session: str | None = Header(None)):
    return S().network(_sid(x_sila_session))


@api.get("/api/moves")
def moves(x_sila_session: str | None = Header(None)):
    return S().moves_today(_sid(x_sila_session))


@api.post("/api/moves/{move_id}/decision")
def decide(body: Decision, move_id: str = P(..., pattern=MOVE_ID), x_sila_session: str | None = Header(None)):
    return _decide(move_id, body, x_sila_session)


def _decide(move_id: str, body: Decision, x_sila_session: str | None = Header(None)):
    sid = _sid(x_sila_session)
    if not sid:
        raise HTTPException(400, "X-Sila-Session header required")
    if move_id not in S().moves:
        raise HTTPException(404, "move not found")
    return S().decide(sid, move_id, body.party, body.decision)


@api.post("/api/session/reset")
def reset(x_sila_session: str | None = Header(None)):
    sid = _sid(x_sila_session)
    if sid:
        S().reset(sid)
    return {"ok": True}


@api.get("/api/session/audit")
def audit(x_sila_session: str | None = Header(None)):
    sid = _sid(x_sila_session)
    return S().audit.events(sid) if sid else []


@api.post("/api/whatif")
def whatif(body: WhatIf, x_sila_session: str | None = Header(None)):
    if body.business not in S().idx:
        raise HTTPException(404, "business not found")
    return S().whatif(_sid(x_sila_session), body.business, body.sales_change, body.late_days, body.late_payer,
                      body.expense, body.expense_day)


@api.get("/api/invoices/{invoice_id}/why")
def invoice_why(invoice_id: str = P(..., pattern=r"^INV\d{6}(-P\d+)?$"), x_sila_session: str | None = Header(None)):
    try:
        return S().invoice_why(invoice_id, _sid(x_sila_session))
    except KeyError:
        raise HTTPException(404, "open invoice not found") from None


@api.get("/api/proof")
def proof():
    return S().proof()


WEB = Path(__file__).resolve().parent.parent / "web"
if WEB.exists():
    api.mount("/", StaticFiles(directory=WEB, html=True), name="web")
