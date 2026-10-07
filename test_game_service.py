# app/tests/test_game_service.py
# Requires the stop_session patch (close_active_game) for test_stop_session_closes_active_game.
import os
import tempfile
from datetime import datetime, timedelta, timezone
from decimal import Decimal

# app.database / app.core.config validate env at import time.
os.environ.setdefault("DATABASE_URL", f"sqlite:///{tempfile.gettempdir()}/billiard_test_import.db")
os.environ.setdefault("OPENAI_API_KEY", "test")
os.environ.setdefault("SECRET_KEY", "test")

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base
import app.billiard.models
from app.billiard.models import BilliardTable, GameStatus, SessionStatus
from app.billiard.services.game_service import game_service
from app.billiard.services.session_service import session_service
from app.billiard.services.table_service import table_service
from app.user.models.user import User


@pytest.fixture()
def db():
    engine = create_engine("sqlite://", poolclass=StaticPool, connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    s = sessionmaker(bind=engine, autoflush=False)()
    yield s
    s.close()


def _user(db, client_id="c1", name="u1"):
    u = User(client_id=client_id, username=name, email=f"{name}@x.com", hashed_password="x")
    db.add(u)
    db.flush()
    return u


@pytest.fixture()
def ctx(db):
    user = _user(db)
    table = BilliardTable(name="T1", client_id=user.client_id, hourly_rate=Decimal("100000"))
    db.add(table)
    db.flush()
    session = table_service.start_session(db, table.id, user)
    db.commit()
    return user, session


def test_start_game_numbers_from_one(db, ctx):
    user, session = ctx
    g = game_service.start_game(db, session.id, user)
    assert (g.game_number, g.player_a_score, g.player_b_score, g.status) == (1, 0, 0, GameStatus.ACTIVE)


def test_second_active_game_rejected(db, ctx):
    user, session = ctx
    game_service.start_game(db, session.id, user)
    with pytest.raises(HTTPException) as e:
        game_service.start_game(db, session.id, user)
    assert e.value.status_code == 409


def test_score_up_down_and_never_negative(db, ctx):
    user, session = ctx
    g = game_service.start_game(db, session.id, user)
    game_service.change_score(db, g.id, "A", 1, user)
    game_service.change_score(db, g.id, "A", 1, user)
    game_service.change_score(db, g.id, "B", 1, user)
    g = game_service.change_score(db, g.id, "A", -1, user)
    assert (g.player_a_score, g.player_b_score) == (1, 1)

    game_service.change_score(db, g.id, "B", -1, user)
    with pytest.raises(HTTPException) as e:
        game_service.change_score(db, g.id, "B", -1, user)
    assert e.value.status_code == 409
    assert db.get(type(g), g.id).player_b_score == 0


def test_reset_score(db, ctx):
    user, session = ctx
    g = game_service.start_game(db, session.id, user)
    game_service.change_score(db, g.id, "A", 5, user)
    g = game_service.reset_score(db, g.id, user)
    assert (g.player_a_score, g.player_b_score) == (0, 0)


def test_new_game_keeps_session_and_billing(db, ctx):
    user, session = ctx
    g1 = game_service.start_game(db, session.id, user)
    game_service.change_score(db, g1.id, "A", 3, user)
    start, rate = session.start_time, session.hourly_rate

    finished, started = game_service.new_game(db, g1.id, user)

    assert finished.status == GameStatus.COMPLETED and finished.end_time is not None
    assert finished.player_a_score == 3                       # history preserved
    assert (started.game_number, started.player_a_score) == (2, 0)
    db.refresh(session)
    assert session.status == SessionStatus.ACTIVE and session.end_time is None
    assert session.start_time == start and session.hourly_rate == rate
    assert [g.game_number for g in game_service.list_games(db, session.id, user)] == [1, 2]


def test_cannot_score_a_finished_game(db, ctx):
    user, session = ctx
    g = game_service.start_game(db, session.id, user)
    game_service.finish_game(db, g.id, user)
    with pytest.raises(HTTPException) as e:
        game_service.change_score(db, g.id, "A", 1, user)
    assert e.value.status_code == 409


def test_other_tenant_gets_404(db, ctx):
    user, session = ctx
    g = game_service.start_game(db, session.id, user)
    intruder = _user(db, client_id="c2", name="u2")
    with pytest.raises(HTTPException) as e:
        game_service.change_score(db, g.id, "A", 1, intruder)
    assert e.value.status_code == 404
    with pytest.raises(HTTPException) as e:
        game_service.start_game(db, session.id, intruder)
    assert e.value.status_code == 404


def test_unknown_game_404(db, ctx):
    user, _ = ctx
    with pytest.raises(HTTPException) as e:
        game_service.reset_score(db, 9999, user)
    assert e.value.status_code == 404


def test_device_clock_before_start_is_clamped(db, ctx):
    user, session = ctx
    skewed = datetime.now(timezone.utc) - timedelta(days=30)
    g = game_service.start_game(db, session.id, user, at=skewed)
    assert g.start_time.replace(tzinfo=timezone.utc) >= session.start_time.replace(tzinfo=timezone.utc)
    g = game_service.finish_game(db, g.id, user, at=skewed)
    assert g.end_time >= g.start_time


def test_stop_session_closes_active_game(db, ctx):
    user, session = ctx
    g = game_service.start_game(db, session.id, user)
    session_service.stop_session(db, session.id, user)
    db.refresh(g)
    assert g.status == GameStatus.COMPLETED and g.end_time is not None
    with pytest.raises(HTTPException):
        game_service.start_game(db, session.id, user)       # session no longer active
