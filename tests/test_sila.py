import os

import numpy as np
import pytest

os.environ.setdefault("SILA_DB", "/tmp/sila_test_audit.db")
os.environ.setdefault("SILA_WARMUP", "0")

from sila import forecast, ledger, synth  # noqa: E402
from sila.config import HORIZON, TODAY  # noqa: E402
from sila.mesh import SAFE_P, Mesh  # noqa: E402


@pytest.fixture(scope="session")
def world():
    return synth.ensure()


@pytest.fixture(scope="session")
def F(world):
    return forecast.Forecaster(ledger.Ledger.build(world)).load()


@pytest.fixture(scope="session")
def today():
    return ledger.day_index(TODAY)


@pytest.fixture(scope="session")
def fc(F, today):
    return F.forecast(today)


@pytest.fixture(scope="session")
def proposals(F, fc, today):
    m = Mesh(F)
    moves = m.propose(fc)
    moves, after = m.verify(today, F.led, moves, fc)
    return moves, after


def network_links(F):
    inv = F.led.inv
    return inv[(inv.payer_i >= 0) & (inv.payee_i >= 0)]


# --- synthetic network ---------------------------------------------------------------------

def test_network_shape(world):
    assert len(world.smes) == 240
    ids = {s["id"] for s in world.smes}
    for s in world.smes:
        assert set(s["network_suppliers"]) <= ids
        for sup in s["network_suppliers"]:   # links are recorded on both sides
            assert s["id"] in next(x for x in world.smes if x["id"] == sup)["network_customers"]


def test_generator_is_deterministic():
    a, b = synth.generate(n=30), synth.generate(n=30)
    assert a.invoices.amount.sum() == b.invoices.amount.sum()
    assert a.flows.amount.sum() == b.flows.amount.sum()


# --- ledger: Sila only changes *when* existing money moves --------------------------------

def test_moving_a_network_invoice_never_creates_money(F):
    led = F.led.copy()
    total_before = led.balance.sum(axis=0)
    row = network_links(F).index[100]
    old = int(led.inv.loc[row, "t_settle"])
    led.resettle(row, max(old - 20, 1))
    assert np.allclose(led.balance.sum(axis=0), total_before)
    led.adjust(0, 200, -50.0)        # discount paid by the receiver ...
    led.adjust(1, 200, 50.0)         # ... is received by the payer
    assert np.allclose(led.balance.sum(axis=0), total_before)


def test_partial_resettle_splits_the_invoice(F):
    led = F.led.copy()
    row = network_links(F).index[200]
    amt = float(led.inv.loc[row, "amount"])
    new_row = led.resettle(row, 300, amount=amt / 4)
    assert new_row != row
    assert led.inv.loc[row, "amount"] + led.inv.loc[new_row, "amount"] == pytest.approx(amt)
    assert bool(led.inv.loc[new_row, "agreed"])


def test_ledger_copy_is_independent(F):
    a = F.led.copy()
    before = F.led.balance.copy()
    a.adjust(3, 10, 1_000.0)
    assert np.array_equal(F.led.balance, before)


# --- forecast ------------------------------------------------------------------------------

def test_forecast_is_well_formed(fc):
    assert fc.p_short.shape == (240,)
    assert ((fc.p_short >= 0) & (fc.p_short <= 1)).all()
    assert fc.q10.shape == (240, HORIZON)
    assert (fc.q10 <= fc.q50 + 1e-6).all() and (fc.q50 <= fc.q90 + 1e-6).all()


def test_forecast_is_reproducible(F, today):
    a, b = F.forecast(today), F.forecast(today)
    assert np.array_equal(a.p_short, b.p_short)


def test_whatif_hooks_move_the_forecast_the_right_way(F, today, fc):
    n = len(F.led.ids)
    i = int(np.argsort(fc.p_short)[len(fc.p_short) // 2])
    worse_sales = np.ones(n)
    worse_sales[i] = 0.2
    extra = np.zeros((n, HORIZON))
    extra[i, 5] = 5 * abs(fc.balance[i]) + 50_000
    worse = F.forecast(today, sales_factor=worse_sales, extra_out=extra)
    assert worse.p_short[i] >= fc.p_short[i]
    assert worse.q50[i, -1] < fc.q50[i, -1]


def test_payment_timing_is_never_in_the_past(F, today):
    op = F.led.open_invoices(today).head(500)
    q = F.predict_delay(op, today)
    assert (q >= 1).all() and (q[:, 0] <= q[:, 1]).all() and (q[:, 1] <= q[:, 2]).all()


# --- the mesh ------------------------------------------------------------------------------

def test_today_has_suggestions_and_they_help(proposals):
    moves, _ = proposals
    assert moves
    improved = [m for m in moves if m.verified["p_short_after"] < m.verified["p_short_before"]
                or m.verified["gap_after"] < m.verified["gap_before"]]
    assert len(improved) == len(moves)


def test_helpers_stay_safe(proposals):
    moves, after = proposals
    for m in moves:
        assert m.verified["helper_p_after"] < max(SAFE_P, m.verified["helper_p_before"] + 0.05)
        assert m.helper_buffer_days >= 10 - 1e-6


def test_only_network_invoices_are_used_and_each_once(proposals, F):
    moves, _ = proposals
    rows = [leg.row for m in moves for leg in m.legs]
    assert len(rows) == len(set(rows))
    inv = F.led.inv
    for m in moves:
        for leg in m.legs:
            r = inv.loc[leg.row]
            assert r.payer_i >= 0 and r.payee_i >= 0 and not bool(r.agreed)


def test_grace_is_free_and_early_payment_is_cheaper_than_a_loan(proposals):
    moves, _ = proposals
    for m in moves:
        if m.kind == "grace":
            assert m.fee == 0
        else:
            assert m.fee < m.loan_cost


def test_applying_moves_never_creates_money(proposals, F, today):
    moves, _ = proposals
    led = Mesh.apply(F.led.copy(), moves, today)
    assert np.allclose(led.balance.sum(axis=0), F.led.balance.sum(axis=0))


def test_one_suggestion_per_pair(proposals):
    moves, _ = proposals
    keys = [(m.helps, m.helper, m.kind) for m in moves if m.kind != "chain"]
    assert len(keys) == len(set(keys))


# --- six-month replay (built by scripts.build) ------------------------------------------------

def test_replay_never_harmed_a_helper():
    import json

    from sila.config import ARTIFACTS
    m = json.loads((ARTIFACTS / "replay_metrics.json").read_text())
    assert m["helpers_pushed_into_shortfall"] == 0
    assert m["new_debt_created"] == 0
    assert m["episodes_prevented_share"] > 0.3


# --- API -----------------------------------------------------------------------------------

@pytest.fixture(scope="session")
def client():
    from fastapi.testclient import TestClient

    from sila.api import api
    return TestClient(api)


H = {"X-Sila-Session": "testsession0001"}


def test_api_reads(client):
    assert client.get("/health").json()["status"] == "ok"
    o = client.get("/api/overview").json()
    assert o["businesses"] == 240 and o["moves_today"] > 0
    rows = client.get("/api/businesses?status=at_risk").json()["rows"]
    assert rows and all(r["status"] == "at_risk" for r in rows)
    assert client.get("/").status_code == 200
    assert client.get("/api/network").json()["nodes"]
    assert client.get("/api/proof").json()["weeks"]


def test_api_never_leaks_the_future(client):
    """Actual settlement dates of open invoices are the future: the API must only expose predictions."""
    b = client.get("/api/businesses/S0050").json()
    import json
    text = json.dumps(b)
    assert '"paid"' not in text and "t_settle" not in text and "t_paid" not in text


def test_api_validation(client):
    assert client.get("/api/businesses/S1").status_code == 422
    assert client.get("/api/businesses/S9999").status_code == 404
    assert client.get("/api/businesses?sort=drop").status_code == 422
    assert client.post("/api/whatif", json={"business": "S0050", "sales_change": -5}).status_code == 422
    assert client.post("/api/moves/M0001-01/decision", json={"party": "helped", "decision": "accept"}).status_code in (400, 404)
    assert client.get("/api/overview", headers={"X-Sila-Session": "bad id!"}).status_code == 422
    assert client.get("/api/invoices/INV999999/why").status_code == 404


def test_consent_needs_both_owners_and_is_private(client):
    client.post("/api/session/reset", headers=H)
    mv = client.get("/api/moves").json()["moves"][0]
    url = f"/api/moves/{mv['id']}/decision"
    r = client.post(url, json={"party": "helped", "decision": "accept"}, headers=H).json()
    assert r["move"]["status"] == "waiting" and r.get("impact") is None
    r = client.post(url, json={"party": "helper", "decision": "accept"}, headers=H).json()
    assert r["move"]["status"] == "agreed"
    assert r["impact"]["helps"]["after"] <= r["impact"]["helps"]["before"]
    assert client.get("/api/overview", headers=H).json()["moves_agreed"] == 1
    assert client.get("/api/overview", headers={"X-Sila-Session": "someoneelse01"}).json()["moves_agreed"] == 0
    events = client.get("/api/session/audit", headers=H).json()
    assert [e["decision"] for e in events][-2:] == ["accept", "accept"]
    client.post("/api/session/reset", headers=H)
    assert client.get("/api/overview", headers=H).json()["moves_agreed"] == 0


def test_security_headers(client):
    r = client.get("/api/overview")
    assert r.headers["x-content-type-options"] == "nosniff"
    assert "frame-ancestors" in r.headers["content-security-policy"]
    assert r.headers["cache-control"] == "no-store"


def test_rate_limit_blocks_floods():
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from sila.hardening import RateLimit
    app = FastAPI()
    app.add_middleware(RateLimit, reads_per_min=3, writes_per_min=1)

    @app.get("/ping")
    def ping():
        return {"ok": True}

    c = TestClient(app)
    codes = [c.get("/ping").status_code for _ in range(5)]
    assert codes[:3] == [200] * 3 and codes[-1] == 429
