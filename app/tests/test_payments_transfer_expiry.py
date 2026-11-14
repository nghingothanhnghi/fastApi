# app/tests/test_payments_transfer_expiry.py
# Expiry of stale bank-transfer lines (background job) and the manager's pending-lines list.
# Runs against the FAKE business (payments_testkit); no billiard involved.
from datetime import datetime, timedelta, timezone

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
from sqlalchemy.orm import sessionmaker

from app.database import get_db
from app.payments import config
from app.payments.models.order import PaymentLine
from app.payments.models.payment import PaymentStatus, PaymentTransaction
from app.payments.routes.bank_feed_router import router as bank_feed_router
from app.payments.services.bank_feed_service import bank_feed_service as feed
from app.payments.services.order_service import payment_order_service as svc
from app.tests.payments_testkit import (  # noqa: F401  (fixtures are used by name)
    CLIENT, D, FAKE, cashier, db, engine, events, fake, make_user, manager, pay, view,
)
from app.user.utils.token import get_current_user

ACCOUNT = "0123456789"


@pytest.fixture(autouse=True)
def bank(monkeypatch):
    monkeypatch.setattr(config, "BANK_BIN", "970436")
    monkeypatch.setattr(config, "BANK_ACCOUNT_NO", ACCOUNT)
    monkeypatch.setattr(config, "BANK_CODE", "VCB")
    monkeypatch.setattr(config, "BANK_ACCOUNT_NAME", "BIDA CLUB")
    monkeypatch.setattr(config, "TRANSFER_AUTO_CANCEL_GRACE_MINUTES", 60)


def _now():
    return datetime.now(timezone.utc)


def _transfer_line(db, user, fake, total="310000"):
    bill_id = fake.create(total)
    pay(db, user, bill_id, payment_method="bank_transfer")
    return bill_id, view(db, user, bill_id)["payments"][0]


def _expired(db, line_id, minutes_ago):
    """Pretend the line's QR expired `minutes_ago` minutes ago."""
    line = db.get(PaymentLine, line_id)
    line.expires_at = _now() - timedelta(minutes=minutes_ago)
    db.commit()


# ------------------------------------------------------------------ expiry job

def test_line_expired_past_the_grace_period_is_cancelled_and_the_bill_reopens(db, cashier, fake):
    bill_id, line = _transfer_line(db, cashier, fake)
    _expired(db, line["id"], minutes_ago=61)

    assert svc.expire_stale_transfer_lines(db) == 1

    db.expire_all()
    v = view(db, cashier, bill_id)
    assert v["payments"][0]["status"] == "cancelled"
    assert v["payments"][0]["note"] == "Transfer not received in time"
    assert v["state"] == "unpaid"                       # the cashier can start over
    assert fake.bills[int(bill_id)].state == "unpaid"   # mirrored onto the business object
    assert "line_expired" in events(db, bill_id)


def test_expired_line_is_kept_during_the_grace_period(db, cashier, fake):
    bill_id, line = _transfer_line(db, cashier, fake)
    _expired(db, line["id"], minutes_ago=10)            # QR expired, but a slow bank webhook may still come

    assert svc.expire_stale_transfer_lines(db) == 0

    db.expire_all()
    assert view(db, cashier, bill_id)["payments"][0]["status"] == "pending"


def test_line_that_has_not_expired_is_untouched(db, cashier, fake):
    bill_id, line = _transfer_line(db, cashier, fake)
    assert svc.expire_stale_transfer_lines(db, now=_now() + timedelta(minutes=10)) == 0
    db.expire_all()
    assert view(db, cashier, bill_id)["payments"][0]["status"] == "pending"


def test_grace_zero_turns_the_job_off(db, cashier, fake, monkeypatch):
    monkeypatch.setattr(config, "TRANSFER_AUTO_CANCEL_GRACE_MINUTES", 0)
    bill_id, line = _transfer_line(db, cashier, fake)
    _expired(db, line["id"], minutes_ago=24 * 60)
    assert svc.expire_stale_transfer_lines(db) == 0
    db.expire_all()
    assert view(db, cashier, bill_id)["payments"][0]["status"] == "pending"


def test_paid_line_is_never_expired(db, cashier, fake):
    bill_id, line = _transfer_line(db, cashier, fake)
    svc.confirm_transfer(db, FAKE, bill_id, line["id"], cashier)
    _expired(db, line["id"], minutes_ago=24 * 60)

    assert svc.expire_stale_transfer_lines(db) == 0

    db.expire_all()
    v = view(db, cashier, bill_id)
    assert v["payments"][0]["status"] == "completed" and v["state"] == "paid"


def test_expiry_does_not_touch_cash_lines_or_other_pending_transfers(db, cashier, fake):
    stale_bill, stale = _transfer_line(db, cashier, fake)
    fresh_bill, fresh = _transfer_line(db, cashier, fake)
    _expired(db, stale["id"], minutes_ago=120)

    assert svc.expire_stale_transfer_lines(db) == 1

    db.expire_all()
    assert view(db, cashier, stale_bill)["payments"][0]["status"] == "cancelled"
    assert view(db, cashier, fresh_bill)["payments"][0]["status"] == "pending"


def test_split_bill_keeps_its_paid_part_when_the_transfer_part_expires(db, cashier, fake):
    bill_id = fake.create("310000")
    pay(db, cashier, bill_id, payments=[
        {"method": "cash", "amount": "200000"}, {"method": "bank_transfer", "amount": "110000"},
    ])
    transfer = next(p for p in view(db, cashier, bill_id)["payments"] if p["method"] == "bank_transfer")
    _expired(db, transfer["id"], minutes_ago=120)

    assert svc.expire_stale_transfer_lines(db) == 1

    db.expire_all()
    v = view(db, cashier, bill_id)
    assert v["state"] == "pending"                      # part paid, 110000 still due
    assert {p["method"]: p["status"] for p in v["payments"]} == {"cash": "completed", "bank_transfer": "cancelled"}


def test_money_arriving_after_the_line_was_cancelled_goes_to_the_manager(db, cashier, fake):
    from app.tests.test_payments_bank_feed import _tx
    bill_id, line = _transfer_line(db, cashier, fake)
    _expired(db, line["id"], minutes_ago=120)
    svc.expire_stale_transfer_lines(db)

    tx, _ = feed.process_sepay(db, _tx(1, line["transfer"]["memo"]))

    assert tx.status == "needs_review" and "cancelled" in tx.reason


def test_a_transfer_confirmed_just_before_the_job_runs_is_not_cancelled(db, cashier, fake):
    bill_id, line = _transfer_line(db, cashier, fake)
    _expired(db, line["id"], minutes_ago=120)
    cutoff = _now() - timedelta(minutes=60)
    svc.confirm_transfer(db, FAKE, bill_id, line["id"], cashier)     # settled after the job picked it

    assert svc.expire_line(db, line["id"], cutoff) is False

    db.expire_all()
    assert view(db, cashier, bill_id)["payments"][0]["status"] == "completed"


def test_payment_record_of_an_expired_line_is_marked_failed(db, cashier, fake):
    bill_id, line = _transfer_line(db, cashier, fake)
    payment_id = db.get(PaymentLine, line["id"]).payment_id
    _expired(db, line["id"], minutes_ago=120)

    svc.expire_stale_transfer_lines(db)

    db.expire_all()
    payment = db.get(PaymentTransaction, payment_id)
    assert payment.status == PaymentStatus.FAILED


def test_the_job_wrapper_runs_against_its_own_session(engine, db, cashier, fake, monkeypatch):
    from app.payments.jobs import transfer_expiry_job
    bill_id, line = _transfer_line(db, cashier, fake)
    _expired(db, line["id"], minutes_ago=120)
    monkeypatch.setattr(transfer_expiry_job, "SessionLocal", sessionmaker(bind=engine, autoflush=False))

    transfer_expiry_job.expire_stale_transfer_lines_job()

    db.expire_all()
    assert view(db, cashier, bill_id)["payments"][0]["status"] == "cancelled"


# ------------------------------------------------------------- pending lines

def test_only_managers_can_list_pending_lines(db, cashier):
    with pytest.raises(HTTPException) as e:
        feed.list_pending_lines(db, cashier)
    assert e.value.status_code == 403


def test_manager_lists_waiting_transfer_lines_newest_first(db, cashier, manager, fake):
    _, first = _transfer_line(db, cashier, fake, total="100000")
    _, second = _transfer_line(db, cashier, fake, total="250000")

    rows = feed.list_pending_lines(db, manager)

    assert [r["line_id"] for r in rows] == [second["id"], first["id"]]
    top = rows[0]
    assert top["amount"] == D("250000") and top["order_total"] == D("250000")
    assert top["source_type"] == FAKE and top["transfer_memo"] == second["transfer"]["memo"]
    assert top["expired"] is False and top["expires_at"] is not None


def test_pending_lines_can_be_filtered_by_exact_amount(db, cashier, manager, fake):
    _transfer_line(db, cashier, fake, total="100000")
    _, wanted = _transfer_line(db, cashier, fake, total="250000")

    rows = feed.list_pending_lines(db, manager, amount=D("250000"))

    assert [r["line_id"] for r in rows] == [wanted["id"]]
    assert feed.list_pending_lines(db, manager, amount=D("999")) == []


def test_pending_lines_exclude_paid_and_cancelled_lines_and_flag_expired_ones(db, cashier, manager, fake):
    paid_bill, paid = _transfer_line(db, cashier, fake)
    svc.confirm_transfer(db, FAKE, paid_bill, paid["id"], cashier)
    cancelled_bill, cancelled = _transfer_line(db, cashier, fake)
    svc.cancel_line(db, FAKE, cancelled_bill, cancelled["id"], cashier, "paid cash instead")
    _, waiting = _transfer_line(db, cashier, fake)
    _expired(db, waiting["id"], minutes_ago=5)           # QR expired, still waiting (inside the grace period)

    rows = feed.list_pending_lines(db, manager)

    assert [(r["line_id"], r["expired"]) for r in rows] == [(waiting["id"], True)]


def test_pending_lines_are_scoped_to_the_managers_club(db, cashier, manager, fake):
    _transfer_line(db, cashier, fake)
    rival = make_user(db, "rival", role="manager", client="other")
    assert feed.list_pending_lines(db, rival) == []
    assert len(feed.list_pending_lines(db, manager)) == 1


def test_a_listed_line_can_be_assigned_a_matching_bank_transaction(db, cashier, manager, fake):
    from app.tests.test_payments_bank_feed import _tx
    bill_id, line = _transfer_line(db, cashier, fake)
    tx, _ = feed.process_sepay(db, _tx(1, "no code here", amount=310000, content="chuyen tien"))
    assert tx.status == "unmatched"

    wanted = feed.list_pending_lines(db, manager, amount=tx.amount)
    feed.assign(db, tx.id, wanted[0]["line_id"], manager)

    db.expire_all()
    assert view(db, cashier, bill_id)["state"] == "paid"


@pytest.fixture()
def client(engine):
    Session = sessionmaker(bind=engine, autoflush=False)
    app = FastAPI()
    app.include_router(bank_feed_router)
    app.dependency_overrides[get_db] = lambda: Session()
    return app, TestClient(app)


def test_pending_lines_http_route(client, db, cashier, manager, fake):
    app, http = client
    _, line = _transfer_line(db, cashier, fake, total="250000")

    app.dependency_overrides[get_current_user] = lambda: cashier
    assert http.get("/payments/bank-feed/pending-lines").status_code == 403

    app.dependency_overrides[get_current_user] = lambda: manager
    r = http.get("/payments/bank-feed/pending-lines", params={"amount": "250000", "limit": 10})
    assert r.status_code == 200
    body = r.json()
    assert [row["line_id"] for row in body] == [line["id"]]
    assert body[0]["transfer_memo"] == line["transfer"]["memo"] and body[0]["expired"] is False
    assert http.get("/payments/bank-feed/pending-lines", params={"limit": 0}).status_code == 422
