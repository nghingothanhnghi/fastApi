# app/tests/_billiard_fixtures.py
# Shared helpers for the billiard tests written after the roadmap (table status,
# cancel, discount, packages, ...). Same in-memory SQLite setup as test_game_service.py.
# Usage in a test module:
#     from app.tests._billiard_fixtures import *   # noqa: F401,F403  (db fixture + helpers)
import os
import tempfile

# app.database / app.core.config validate env at import time.
os.environ.setdefault("DATABASE_URL", f"sqlite:///{tempfile.gettempdir()}/billiard_test_import.db")
os.environ.setdefault("OPENAI_API_KEY", "test")
os.environ.setdefault("SECRET_KEY", "test")

from decimal import Decimal

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import app.tests._load_models  # noqa: F401  (registers every model so relationships resolve)
from app.billiard.models import BilliardTable
from app.database import Base
from app.user.models.user import User

__all__ = ["db", "make_user", "make_table", "Decimal"]


@pytest.fixture()
def db():
    engine = create_engine("sqlite://", poolclass=StaticPool, connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    s = sessionmaker(bind=engine, autoflush=False)()
    yield s
    s.close()


def make_user(db, client_id="c1", name="u1"):
    u = User(client_id=client_id, username=name, email=f"{name}@x.com", hashed_password="x")
    db.add(u)
    db.flush()
    return u


def make_table(db, client_id="c1", name="T1", rate="100000"):
    t = BilliardTable(name=name, client_id=client_id, hourly_rate=Decimal(rate))
    db.add(t)
    db.flush()
    return t
