# app/tests/test_pricing_sessions.py
# Pricing rules wired into the session lifecycle: the rule is chosen at START
# (by start time, club-local), frozen into the session, and used for the final
# bill (finalize_stop) and the live total (table_service.get_active_tables).
import os
import tempfile
from datetime import datetime, time, timedelta, timezone
from decimal import Decimal

# app.database / app.core.config validate env at import time.
os.environ.setdefault("DATABASE_URL", f"sqlite:///{tempfile.gettempdir()}/billiard_test_import.db")
os.environ.setdefault("OPENAI_API_KEY", "test")
os.environ.setdefault("SECRET_KEY", "test")

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base
import app.billiard.models  # noqa: F401  (registers billiard tables)
from app.billiard import config
from app.billiard.models import BilliardTable, PricingRule, PricingRuleType, SessionStatus
from app.payments.models.payment import PaymentTransaction  # noqa: F401
from app.product.models.product import Product, ProductVariant  # noqa: F401  (session_items FK)
from app.user.models.user import User
from app.user.models.role import Role  # noqa: F401
from app.user.models.user_role import UserRole  # noqa: F401
from app.hydro_system.models.device import HydroDevice  # noqa: F401
from app.hydro_system.models.actuator import HydroActuator  # noqa: F401
from app.hydro_system.models.actuator_log import HydroActuatorLog  # noqa: F401
from app.hydro_system.models.schedule import HydroSchedule  # noqa: F401
from app.billiard.services.session_lifecycle import finalize_stop, open_session
from app.billiard.services.table_service import table_service

CLIENT = "c1"


@pytest.fixture()
def db():
    engine = create_engine(
        "sqlite://", poolclass=StaticPool, connect_args={"check_same_thread": False},
    )
    Base.metadata.create_all(engine)
    s = sessionmaker(bind=engine, autoflush=False)()
    yield s
    s.close()


def _table(db, rate="100000", name="T1"):
    t = BilliardTable(name=name, hourly_rate=Decimal(rate), client_id=CLIENT)
    db.add(t)
    db.flush()
    return t


def _rule(db, rule_type, rate=None, params=None, start=None, end=None,
          table_id=None, priority=0, name="rule", days=None):
    r = PricingRule(
        client_id=CLIENT, table_id=table_id, name=name, rule_type=rule_type,
        hourly_rate=Decimal(rate) if rate is not None else None, params=params,
        start_time=start, end_time=end, days_of_week=days, priority=priority,
    )
    db.add(r)
    db.flush()
    return r


def _local(hour, minute=0, days_ago=3):
    """A PAST club-local wall-clock time as UTC. (resolve_time clamps the future to now.)"""
    day = (datetime.now(config.LOCAL_TZ) - timedelta(days=days_ago)).date()
    return datetime.combine(day, time(hour, minute), tzinfo=config.LOCAL_TZ).astimezone(timezone.utc)


def _play(db, table, start, minutes):
    s = open_session(db, table, None, at=start)
    finalize_stop(db, s, table, None, at=start + timedelta(minutes=minutes))
    return s


# ---------------------------------------------------------------- happy hour

def test_happy_hour_rate_applies_when_started_inside_window(db):
    table = _table(db)   # normal rate 100000/h
    rule = _rule(db, PricingRuleType.PER_MINUTE, rate="60000",
                 start=time(18, 0), end=time(20, 0), name="Happy hour")

    s = open_session(db, table, None, at=_local(18, 30))

    assert s.hourly_rate == Decimal("60000")
    assert s.billing_policy == "per_minute"
    assert s.pricing_snapshot["rule_id"] == rule.id
    assert s.pricing_snapshot["rule_name"] == "Happy hour"
    assert s.pricing_snapshot["hourly_rate"] == "60000"

    finalize_stop(db, s, table, None, at=_local(19, 30))
    assert s.duration_minutes == 60
    assert s.total_table_fee == Decimal("60000")
    assert s.grand_total == Decimal("60000")
    assert s.status == SessionStatus.COMPLETED


def test_happy_hour_not_applied_outside_window(db):
    table = _table(db)
    _rule(db, PricingRuleType.PER_MINUTE, rate="60000", start=time(18, 0), end=time(20, 0))

    s = _play(db, table, _local(21, 0), 60)

    assert s.hourly_rate == Decimal("100000")
    assert s.pricing_snapshot["rule_id"] is None
    assert s.total_table_fee == Decimal("100000")


def test_happy_hour_rate_kept_when_session_runs_past_the_window(db):
    """The rule is chosen once, at start: 19:30 -> 20:30 is billed entirely at the happy-hour rate."""
    table = _table(db)
    _rule(db, PricingRuleType.PER_MINUTE, rate="60000", start=time(18, 0), end=time(20, 0))

    s = _play(db, table, _local(19, 30), 60)

    assert s.hourly_rate == Decimal("60000")
    assert s.total_table_fee == Decimal("60000")


def test_happy_hour_respects_days_of_week(db):
    table = _table(db)
    start = _local(18, 30)
    weekday = ("mon", "tue", "wed", "thu", "fri", "sat", "sun")[start.astimezone(config.LOCAL_TZ).weekday()]
    other = "mon" if weekday != "mon" else "tue"
    _rule(db, PricingRuleType.PER_MINUTE, rate="60000", start=time(18, 0), end=time(20, 0),
          days=other, name="other day only")
    match = _rule(db, PricingRuleType.PER_MINUTE, rate="50000", start=time(18, 0), end=time(20, 0),
                  days=weekday, name="today")

    s = open_session(db, table, None, at=start)

    assert s.pricing_snapshot["rule_id"] == match.id
    assert s.hourly_rate == Decimal("50000")


def test_table_specific_rule_beats_tenant_wide_rule_of_equal_priority(db):
    t1, t2 = _table(db, name="T1"), _table(db, name="T2")
    _rule(db, PricingRuleType.PER_MINUTE, rate="80000", name="all tables")
    own = _rule(db, PricingRuleType.PER_MINUTE, rate="70000", table_id=t1.id, name="T1 only")

    s1 = open_session(db, t1, None, at=_local(10))
    s2 = open_session(db, t2, None, at=_local(10))

    assert s1.pricing_snapshot["rule_id"] == own.id and s1.hourly_rate == Decimal("70000")
    assert s2.hourly_rate == Decimal("80000")


def test_inactive_rule_is_ignored(db):
    table = _table(db)
    rule = _rule(db, PricingRuleType.PER_MINUTE, rate="60000")
    rule.is_active = False
    db.flush()

    s = open_session(db, table, None, at=_local(10))

    assert s.hourly_rate == Decimal("100000")
    assert s.pricing_snapshot["rule_id"] is None


# --------------------------------------------------------------------- block

def test_block_pricing_rounds_up_to_whole_blocks(db):
    table = _table(db)   # 100000/h -> a 30-minute block costs 50000
    _rule(db, PricingRuleType.BLOCK, params={"block_minutes": 30})

    assert _play(db, table, _local(10), 10).total_table_fee == Decimal("50000")    # 1 block
    assert _play(db, table, _local(11), 30).total_table_fee == Decimal("50000")    # exactly 1 block
    assert _play(db, table, _local(12), 31).total_table_fee == Decimal("100000")   # 2 blocks
    assert _play(db, table, _local(13), 95).total_table_fee == Decimal("200000")   # 4 blocks


def test_block_rule_snapshot_is_stored_on_the_session(db):
    table = _table(db)
    rule = _rule(db, PricingRuleType.BLOCK, params={"block_minutes": 15}, name="15 min blocks")

    s = open_session(db, table, None, at=_local(10))

    assert s.billing_policy == "block"
    assert s.pricing_snapshot["rule_type"] == "block"
    assert s.pricing_snapshot["params"] == {"block_minutes": 15}
    assert s.pricing_snapshot["rule_id"] == rule.id


def test_block_pricing_defaults_to_60_minute_blocks(db):
    table = _table(db)
    _rule(db, PricingRuleType.BLOCK)   # no params

    assert _play(db, table, _local(10), 61).total_table_fee == Decimal("200000")


def test_block_pricing_adds_products_to_grand_total(db):
    table = _table(db)
    _rule(db, PricingRuleType.BLOCK, params={"block_minutes": 30})
    s = open_session(db, table, None, at=_local(10))
    finalize_stop(db, s, table, None, at=_local(10) + timedelta(minutes=45))

    assert s.total_table_fee == Decimal("100000")
    assert s.grand_total == s.total_table_fee + s.total_product_fee


# ------------------------------------------------- snapshot / history safety

def test_editing_or_deleting_a_rule_does_not_change_a_running_session(db):
    table = _table(db)
    rule = _rule(db, PricingRuleType.PER_MINUTE, rate="60000", start=time(18, 0), end=time(20, 0))
    s = open_session(db, table, None, at=_local(18, 30))

    rule.hourly_rate = Decimal("10000")
    rule.rule_type = PricingRuleType.BLOCK
    db.flush()
    finalize_stop(db, s, table, None, at=_local(19, 30))
    assert s.total_table_fee == Decimal("60000")

    db.delete(rule)
    db.flush()
    assert s.total_table_fee == Decimal("60000")


def test_session_without_rules_keeps_old_behaviour(db):
    table = _table(db)   # no PricingRule rows at all

    s = _play(db, table, _local(10), 90)

    assert s.hourly_rate == Decimal("100000")
    assert s.billing_policy == config.BILLING_POLICY.value
    assert s.total_table_fee == Decimal("150000")   # per_minute default: 1.5 h


def test_legacy_session_without_snapshot_still_bills_by_policy(db):
    table = _table(db)
    s = open_session(db, table, None, at=_local(10))
    s.pricing_snapshot = None          # a session created before pricing rules existed
    s.billing_policy = "rounded_hour"
    finalize_stop(db, s, table, None, at=_local(10) + timedelta(minutes=61))

    assert s.total_table_fee == Decimal("200000")   # 2 started hours


# ------------------------------------------------------------ live total

def test_live_total_matches_the_rule_used_for_the_final_bill(db):
    user = User(client_id=CLIENT, username="u1", email="u1@x.com", hashed_password="x")
    db.add(user)
    table = _table(db)
    _rule(db, PricingRuleType.BLOCK, params={"block_minutes": 30})
    open_session(db, table, user.id)   # starts now

    live = table_service.get_active_tables(db, user)

    assert len(live) == 1
    assert live[0]["current_table_fee"] == Decimal("50000")    # first 30-min block, not 1/60 of an hour
    assert live[0]["current_total"] == Decimal("50000")


def test_live_total_uses_happy_hour_snapshot_rate(db):
    user = User(client_id=CLIENT, username="u1", email="u1@x.com", hashed_password="x")
    db.add(user)
    table = _table(db)
    _rule(db, PricingRuleType.PER_MINUTE, rate="60000")   # all-day "discount" rate
    start = datetime.now(timezone.utc) - timedelta(minutes=30)
    open_session(db, table, user.id, at=start)

    live = table_service.get_active_tables(db, user)

    assert live[0]["hourly_rate"] == Decimal("60000")
    # 30 min at 60000/h = 30000 (31000 if the clock ticked into the next billable minute)
    assert live[0]["current_table_fee"] in (Decimal("30000"), Decimal("31000"))


# ------------------------------------------------------------ bill / receipt

def test_bill_shows_the_pricing_rule_name_and_params(db):
    from app.billiard.services.session_service import session_service
    table = _table(db)
    _rule(db, PricingRuleType.BLOCK, params={"block_minutes": 30}, name="30 min blocks")
    s = _play(db, table, _local(10), 45)

    bill = session_service.build_bill(s)

    assert bill["pricing_rule_name"] == "30 min blocks"
    assert bill["pricing_params"] == {"block_minutes": 30}
    assert bill["billing_policy"] == "block"
    assert bill["total_table_fee"] == Decimal("100000")


def test_bill_without_rule_or_snapshot_has_no_rule_name(db):
    from app.billiard.services.session_service import session_service
    table = _table(db)

    no_rule = _play(db, table, _local(10), 60)
    legacy = _play(db, table, _local(12), 60)
    legacy.pricing_snapshot = None

    for s in (no_rule, legacy):
        bill = session_service.build_bill(s)
        assert bill["pricing_rule_name"] is None
        assert bill["pricing_params"] == {}