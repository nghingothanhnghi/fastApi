# app/tests/test_session_cancel.py
# Roadmap item B: cancel an ACTIVE session opened by mistake (manager only, reason required).
from decimal import Decimal
from types import SimpleNamespace

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.tests._billiard_fixtures import *  # noqa: F401,F403
from app.billiard.models import (
    BilliardDevice, GameStatus, SessionStatus, TableGame, TableSession, TableStatus,
)
from app.billiard.routes.session_router import router
from app.billiard.schemas.event import DeviceEventIn
from app.billiard.services import table_lifecycle
from app.billiard.services.device_auth import hash_api_key
from app.billiard.services.event_service import event_service
from app.billiard.services.game_service import game_service
from app.billiard.services.payment_adapter import billiard_session_payable
from app.billiard.services.report_service import report_service
from app.billiard.services.session_service import session_service
from app.billiard.services.table_service import table_service
from app.database import Base, get_db
from app.product.models.product import Product
from app.user.utils.token import get_current_user


def _active(db, client_id="c1"):
    user = make_user(db, client_id=client_id)
    table = make_table(db, client_id=client_id)
    session = table_service.start_session(db, table.id, user)
    db.commit()
    return user, table, session


def _cancel(db, user, session_id, reason="opened by mistake"):
    return session_service.cancel_session(db, session_id, reason, user)


# ---------------------------------------------------------------- service

def test_cancel_active_session_frees_table(db):
    user, table, s = _active(db)
    cancelled = _cancel(db, user, s.id)
    db.commit()
    db.refresh(table)
    assert cancelled.status == SessionStatus.CANCELLED
    assert table.status == TableStatus.AVAILABLE
    assert cancelled.grand_total == cancelled.total_table_fee == cancelled.total_product_fee == Decimal("0")
    assert cancelled.end_time is not None and cancelled.cancelled_at is not None


def test_cancel_records_who_why_and_when(db):
    user, _, s = _active(db)
    cancelled = _cancel(db, user, s.id, "wrong table")
    assert cancelled.cancelled_by_id == user.id
    assert cancelled.cancel_reason == "wrong table"
    bill = session_service.build_bill(cancelled)
    assert bill["status"] == "cancelled" and bill["cancel_reason"] == "wrong table"
    assert bill["cancelled_by"] == user.username and bill["grand_total"] == Decimal("0")


def test_cancel_closes_running_game_as_cancelled_and_keeps_scores(db):
    user, _, s = _active(db)
    game = game_service.start_game(db, s.id, user)
    game_service.change_score(db, game.id, "A", 1, user)
    db.commit()
    _cancel(db, user, s.id)
    db.commit()
    db.refresh(game)
    assert game.status == GameStatus.CANCELLED
    assert game.player_a_score == 1 and game.end_time is not None


def test_cancel_keeps_finished_games_untouched(db):
    user, _, s = _active(db)
    first = game_service.start_game(db, s.id, user)
    game_service.finish_game(db, first.id, user)
    db.commit()
    _cancel(db, user, s.id)
    db.refresh(first)
    assert first.status == GameStatus.COMPLETED


def test_cancel_keeps_item_rows_but_charges_nothing(db):
    user, _, s = _active(db)
    p = Product(name="Beer", base_price=Decimal("25000"))
    db.add(p)
    db.flush()
    session_service.add_item(db, s.id, p.id, 2, None, user)
    db.commit()
    cancelled = _cancel(db, user, s.id)
    assert len(cancelled.items) == 1                    # kept for audit
    assert cancelled.grand_total == Decimal("0")


def test_cannot_cancel_completed_session(db):
    user, _, s = _active(db)
    session_service.stop_session(db, s.id, user)
    db.commit()
    with pytest.raises(HTTPException) as e:
        _cancel(db, user, s.id)
    assert e.value.status_code == 409 and "active" in e.value.detail


def test_cannot_cancel_twice(db):
    user, _, s = _active(db)
    _cancel(db, user, s.id)
    db.commit()
    with pytest.raises(HTTPException) as e:
        _cancel(db, user, s.id)
    assert e.value.status_code == 409 and "already cancelled" in e.value.detail


def test_cancelled_session_cannot_be_stopped(db):
    user, _, s = _active(db)
    _cancel(db, user, s.id)
    db.commit()
    with pytest.raises(HTTPException) as e:
        session_service.stop_session(db, s.id, user)
    assert e.value.status_code == 409 and "cancelled" in e.value.detail


def test_cancelled_session_cannot_receive_items(db):
    user, _, s = _active(db)
    _cancel(db, user, s.id)
    db.commit()
    p = Product(name="Beer", base_price=Decimal("25000"))
    db.add(p)
    db.flush()
    with pytest.raises(HTTPException) as e:
        session_service.add_item(db, s.id, p.id, 1, None, user)
    assert e.value.status_code == 409 and "active session" in e.value.detail


def test_cancelled_session_cannot_start_a_game(db):
    user, _, s = _active(db)
    _cancel(db, user, s.id)
    db.commit()
    with pytest.raises(HTTPException) as e:
        game_service.start_game(db, s.id, user)
    assert e.value.status_code == 409


def test_cancelled_session_cannot_be_paid(db):
    user, _, s = _active(db)
    _cancel(db, user, s.id)
    db.commit()
    with pytest.raises(HTTPException) as e:
        billiard_session_payable.check_payable(s)
    assert e.value.status_code == 409 and "cancelled" in e.value.detail


def test_cancelled_session_not_in_usage_report(db):
    user, table, s = _active(db)
    _cancel(db, user, s.id)
    db.commit()
    report = report_service.table_usage(db, user)
    assert report.totals.times_played == 0 and report.totals.total_minutes == 0
    assert report.totals.total_revenue == report.totals.unpaid_total == Decimal("0")


def test_table_can_be_started_again_after_cancel(db):
    user, table, s = _active(db)
    _cancel(db, user, s.id)
    db.commit()
    again = table_service.start_session(db, table.id, user)
    db.commit()
    assert again.id != s.id and again.status == SessionStatus.ACTIVE
    active = db.execute(select(TableSession).where(TableSession.status == SessionStatus.ACTIVE)).scalars().all()
    assert len(active) == 1


def test_find_inconsistencies_empty_after_cancel(db):
    user, _, s = _active(db)
    _cancel(db, user, s.id)
    db.commit()
    assert table_lifecycle.find_inconsistencies(db) == []


def test_cancel_other_tenant_404(db):
    _, _, s = _active(db, client_id="c1")
    other = make_user(db, client_id="c2", name="u2")
    with pytest.raises(HTTPException) as e:
        _cancel(db, other, s.id)
    assert e.value.status_code == 404
    db.refresh(s)
    assert s.status == SessionStatus.ACTIVE


# ---------------------------------------------------------------- controller

def test_controller_session_stop_on_cancelled_session_is_not_rebilled(db):
    user, table, s = _active(db)
    device = BilliardDevice(client_id="c1", device_id="DEV1", name="ctrl", api_key_hash=hash_api_key("k"))
    db.add(device)
    db.commit()
    _cancel(db, user, s.id)
    db.commit()

    res = event_service.ingest(db, device, [
        DeviceEventIn(event_id="e1", event="session_stop", device_seq=1, table_id=table.id, data={"session_id": s.id}),
    ])
    assert [c.event_id for c in res.conflicts] == ["e1"], (res.rejected, res.conflicts)
    db.refresh(s)
    assert s.status == SessionStatus.CANCELLED and s.grand_total == Decimal("0")


# ---------------------------------------------------------------- HTTP

def _http_user(role="manager", client_id="c1"):
    return SimpleNamespace(
        id=1, client_id=client_id, username="boss",
        is_super_admin=lambda: False, has_role=lambda r: r == role,
    )


@pytest.fixture()
def client():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    seed = Session()
    user = make_user(seed)
    table = make_table(seed)
    session = table_service.start_session(seed, table.id, user)
    seed.commit()
    sid = session.id
    seed.close()

    app = FastAPI()
    app.include_router(router)

    def _db():
        s = Session()
        try:
            yield s
        finally:
            s.close()

    holder = {"u": _http_user()}
    app.dependency_overrides[get_db] = _db
    app.dependency_overrides[get_current_user] = lambda: holder["u"]
    c = TestClient(app)
    c.sid, c.holder = sid, holder
    return c


def test_http_cancel_returns_cancelled_bill(client):
    r = client.post(f"/sessions/{client.sid}/cancel", json={"reason": "opened by mistake"})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["status"] == "cancelled" and body["cancel_reason"] == "opened by mistake"
    assert Decimal(str(body["grand_total"])) == 0


def test_http_cancel_requires_reason(client):
    assert client.post(f"/sessions/{client.sid}/cancel", json={}).status_code == 422
    assert client.post(f"/sessions/{client.sid}/cancel", json={"reason": "  "}).status_code == 422
    assert client.post(f"/sessions/{client.sid}/cancel", json={"reason": "ab"}).status_code == 422


def test_http_cancel_is_manager_only(client):
    client.holder["u"] = _http_user("staff")
    assert client.post(f"/sessions/{client.sid}/cancel", json={"reason": "mistake"}).status_code == 403


def test_http_pay_cancelled_session_is_409(client):
    client.post(f"/sessions/{client.sid}/cancel", json={"reason": "mistake"})
    r = client.post(f"/sessions/{client.sid}/pay", json={"payment_method": "cash"})
    assert r.status_code == 409, r.text


def test_http_get_bill_of_cancelled_session_still_works(client):
    client.post(f"/sessions/{client.sid}/cancel", json={"reason": "mistake"})
    r = client.get(f"/sessions/{client.sid}")
    assert r.status_code == 200 and r.json()["status"] == "cancelled"
