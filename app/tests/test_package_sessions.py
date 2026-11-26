# app/tests/test_package_sessions.py
# Roadmap item F: packages in billing. The package price covers the first `duration_minutes` of TABLE
# time; time beyond it is billed by the session's own rule; included products are free up to their
# quantity (per session); everything is frozen in the session at start.
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.tests._billiard_fixtures import *  # noqa: F401,F403
from app.billiard.models import (
    BilliardDevice, BilliardPackage, BilliardPackageItem, BilliardTable, PricingRule, PricingRuleType, TableSession,
)
from app.billiard.routes.pricing_router import router as pricing_router
from app.billiard.routes.session_router import router as session_router
from app.billiard.routes.table_router import router as table_router
from app.billiard.schemas.event import DeviceEventIn
from app.billiard.schemas.package import PackageCreate, PackageItemIn, PackageUpdate
from app.billiard.services import session_lifecycle
from app.billiard.services.device_auth import hash_api_key
from app.billiard.services.event_service import event_service
from app.billiard.services.package_service import package_service
from app.billiard.services.session_service import session_service
from app.billiard.services.table_service import table_service
from app.database import Base, get_db
from app.product.models.product import Product
from app.user.utils.token import get_current_user

D = Decimal
T0 = datetime(2026, 1, 5, 10, 0, tzinfo=timezone.utc)      # fixed past start; stop times are T0 + N minutes


def _setup(db, client_id="c1", name="u1"):
    user = make_user(db, client_id=client_id, name=name)
    table = make_table(db, client_id=client_id, name=f"T-{name}")
    db.commit()
    return user, table


def make_product(db, name="Beer", price=20000, active=True):
    p = Product(name=name, base_price=price, is_active=active)
    db.add(p)
    db.flush()
    return p


def make_package(db, client_id="c1", name="1h Combo", minutes=60, price="80000", items=(), active=True):
    pkg = BilliardPackage(client_id=client_id, name=name, duration_minutes=minutes, price=D(price), is_active=active)
    pkg.items = [BilliardPackageItem(product_id=pid, included_quantity=q) for pid, q in items]
    db.add(pkg)
    db.flush()
    return pkg


def make_rule(db, rule_type, params=None, client_id="c1"):
    r = PricingRule(client_id=client_id, name="r", rule_type=rule_type, params=params, priority=0)
    db.add(r)
    db.flush()
    return r


def play(db, table, minutes, package=None, user=None):
    """Open at T0 and stop at T0 + minutes, so the billable minutes are exact."""
    s = session_lifecycle.open_session(db, table, None, at=T0, package=package)
    session_lifecycle.finalize_stop(db, s, table, None, at=T0 + timedelta(minutes=minutes))
    db.commit()
    return s


# ---------------------------------------------------------------- start / snapshot

def test_start_with_package_snapshots_name_price_duration(db):
    user, table = _setup(db)
    beer = make_product(db)
    pkg = make_package(db, items=[(beer.id, 2)])
    s = table_service.start_session(db, table.id, user, package_id=pkg.id)
    assert (s.package_id, s.package_name, s.package_price) == (pkg.id, "1h Combo", D("80000"))
    assert s.package_snapshot == {
        "package_id": pkg.id, "name": "1h Combo", "price": "80000.00", "duration_minutes": 60,
        "items": [{"product_id": beer.id, "included_quantity": 2}],
    }


def test_package_session_gets_ends_at(db):
    user, table = _setup(db)
    pkg = make_package(db, minutes=90)
    s = table_service.start_session(db, table.id, user, package_id=pkg.id)
    ends = s.ends_at if s.ends_at.tzinfo else s.ends_at.replace(tzinfo=timezone.utc)
    start = s.start_time if s.start_time.tzinfo else s.start_time.replace(tzinfo=timezone.utc)
    assert ends - start == timedelta(minutes=90)


def test_start_with_inactive_package_is_400(db):
    user, table = _setup(db)
    pkg = make_package(db, active=False)
    with pytest.raises(HTTPException) as e:
        table_service.start_session(db, table.id, user, package_id=pkg.id)
    assert e.value.status_code == 400
    db.refresh(table)
    assert table.status.value == "available"            # nothing was started


def test_start_with_other_club_package_is_404(db):
    user, table = _setup(db)
    foreign = make_package(db, client_id="c2")
    with pytest.raises(HTTPException) as e:
        table_service.start_session(db, table.id, user, package_id=foreign.id)
    assert e.value.status_code == 404
    with pytest.raises(HTTPException) as e:
        table_service.start_session(db, table.id, user, package_id=9999)
    assert e.value.status_code == 404


def test_package_and_planned_minutes_together_is_rejected_by_lifecycle(db):
    _, table = _setup(db)
    pkg = make_package(db)
    with pytest.raises(ValueError):
        session_lifecycle.open_session(db, table, None, planned_minutes=30, package=pkg)


def test_failed_package_start_leaves_table_available_for_a_retry(db):
    user, table = _setup(db)
    with pytest.raises(HTTPException):
        table_service.start_session(db, table.id, user, package_id=12345)
    assert table_service.start_session(db, table.id, user).table_id == table.id


def test_editing_package_after_start_does_not_change_session(db):
    user, table = _setup(db)
    beer = make_product(db)
    pkg = make_package(db, items=[(beer.id, 2)])
    s = table_service.start_session(db, table.id, user, package_id=pkg.id)
    db.commit()
    package_service.update_package(
        db, pkg.id, PackageUpdate(price=D("1"), duration_minutes=5, items=[]), user)
    package_service.deactivate_package(db, pkg.id, user)
    db.commit()
    session_service.add_item(db, s.id, beer.id, 2, None, user)
    s.start_time = T0                                    # a fixed past start so 90 minutes is real
    session_lifecycle.finalize_stop(db, s, table, None, at=T0 + timedelta(minutes=90))
    assert s.package_snapshot["price"] == "80000.00" and s.package_snapshot["duration_minutes"] == 60
    assert s.total_table_fee == D("130000.00")           # 80,000 + 30 min overtime, NOT 1 + 85 min
    assert s.total_product_fee == D("0")                 # both beers still free


# ---------------------------------------------------------------- the fee

def test_package_fee_inside_duration_is_package_price(db):
    _, table = _setup(db)
    s = play(db, table, 50, make_package(db))
    assert s.total_table_fee == D("80000.00") and s.grand_total == D("80000.00")


def test_exactly_the_package_duration_has_no_overtime(db):
    _, table = _setup(db)
    s = play(db, table, 60, make_package(db))
    assert s.total_table_fee == D("80000.00")


def test_zero_minutes_still_charges_package_price(db):
    """Policy: the package is bought up front, so even an immediate stop costs its price."""
    _, table = _setup(db)
    s = session_lifecycle.open_session(db, table, None, at=T0, package=make_package(db))
    session_lifecycle.finalize_stop(db, s, table, None, at=T0)
    assert s.total_table_fee == D("80000.00")


@pytest.mark.parametrize("rule_type, params, expected", [
    # table rate 100,000/h, package 60 min for 80,000, played 90 min -> 30 min of overtime
    (PricingRuleType.PER_MINUTE, None, "130000.00"),                  # 80,000 + 30/60 * 100,000
    (PricingRuleType.HOURLY, None, "180000.00"),                      # started hour is full
    (PricingRuleType.BLOCK, {"block_minutes": 30}, "130000.00"),      # one 30-min block
    (PricingRuleType.BLOCK, {"block_minutes": 45}, "155000.00"),      # one 45-min block
    (PricingRuleType.MINIMUM_HOUR, {"min_minutes": 60}, "180000.00"), # the rule's floor applies to the overtime
])
def test_overtime_billed_with_session_rule(db, rule_type, params, expected):
    _, table = _setup(db)
    make_rule(db, rule_type, params)
    s = play(db, table, 90, make_package(db))
    assert s.total_table_fee == D(expected)


def test_minimum_hour_rule_does_not_charge_its_floor_when_there_is_no_overtime(db):
    _, table = _setup(db)
    make_rule(db, PricingRuleType.MINIMUM_HOUR, {"min_minutes": 60})
    s = play(db, table, 30, make_package(db, minutes=60))
    assert s.total_table_fee == D("80000.00")


def test_rule_selection_still_runs_with_a_package(db):
    _, table = _setup(db)
    r = PricingRule(client_id="c1", name="Weekend", rule_type=PricingRuleType.PER_MINUTE,
                    hourly_rate=D("60000"), priority=1)
    db.add(r)
    db.flush()
    s = play(db, table, 90, make_package(db))
    assert s.hourly_rate == D("60000") and s.pricing_snapshot["rule_id"] == r.id
    assert s.total_table_fee == D("110000.00")           # 80,000 + 30 min at 60,000/h


def test_package_fee_is_not_rounded_but_overtime_is(db, monkeypatch):
    from app.billiard import config
    monkeypatch.setattr(config, "FEE_ROUNDING_UNIT", D("1000"))
    _, table = _setup(db)
    s = play(db, table, 61, make_package(db, price="79999"))
    assert s.total_table_fee == D("79999.00") + D("2000.00")   # 1 min = 1,666.67 -> 2,000; price kept exact


def test_session_without_package_unchanged(db):
    _, table = _setup(db)
    s = play(db, table, 90)
    assert s.package_snapshot is None and s.package_id is None
    assert s.total_table_fee == D("150000.00")           # 90 min at 100,000/h, per_minute


def test_package_plus_discount(db):
    user, table = _setup(db)
    s = session_lifecycle.open_session(db, table, None, at=T0, package=make_package(db))
    session_lifecycle.apply_discount(s, percent=D("10"), by_id=user.id)
    session_lifecycle.finalize_stop(db, s, table, None, at=T0 + timedelta(minutes=60))
    assert s.total_table_fee == D("80000.00") and s.discount == D("8000.00") and s.grand_total == D("72000.00")


def test_live_total_matches_stop_total_with_package(db):
    user, table = _setup(db)
    pkg = make_package(db)
    s = table_service.start_session(db, table.id, user, package_id=pkg.id)
    s.start_time = datetime.now(timezone.utc) - timedelta(minutes=89, seconds=30)   # mid-minute: 90 either way
    db.commit()
    row = next(r for r in table_service.get_active_tables(db, user) if r["session_id"] == s.id)
    assert row["package_name"] == "1h Combo" and row["overtime_minutes"] == 30
    session_service.stop_session(db, s.id, user)
    assert row["current_table_fee"] == s.total_table_fee == D("130000.00")
    assert row["current_total"] == s.grand_total


# ---------------------------------------------------------------- included products

def _started(db, items, minutes=60):
    user, table = _setup(db)
    beer = make_product(db, "Beer", 20000)
    tea = make_product(db, "Tea", 10000)
    pkg = make_package(db, minutes=minutes, items=[(beer.id, 2)] if items else [])
    s = table_service.start_session(db, table.id, user, package_id=pkg.id)
    db.commit()
    return user, table, s, beer, tea


def test_included_item_is_free_up_to_quantity(db):
    user, _, s, beer, _ = _started(db, True)
    item = session_service.add_item(db, s.id, beer.id, 1, None, user)
    assert item.from_package and item.unit_price == 0 and item.total_price == 0
    assert item.product_name == "Beer (package)" and s.total_product_fee == D("0")


def test_item_over_included_quantity_is_split(db):
    user, _, s, beer, _ = _started(db, True)
    paid = session_service.add_item(db, s.id, beer.id, 3, None, user)
    assert not paid.from_package and paid.quantity == 1 and paid.total_price == D("20000.00")
    free = [i for i in s.items if i.from_package]
    assert len(free) == 1 and free[0].quantity == 2 and free[0].total_price == 0
    assert s.total_product_fee == D("20000.00")
    assert sum(i.quantity for i in s.items) == 3         # the customer got three beers


def test_included_quantity_counts_across_several_add_calls(db):
    user, _, s, beer, _ = _started(db, True)
    session_service.add_item(db, s.id, beer.id, 1, None, user)
    session_service.add_item(db, s.id, beer.id, 1, None, user)
    third = session_service.add_item(db, s.id, beer.id, 1, None, user)
    assert not third.from_package and third.total_price == D("20000.00")
    assert sum(i.quantity for i in s.items if i.from_package) == 2
    assert s.total_product_fee == D("20000.00")


def test_non_package_product_is_charged_normally(db):
    user, _, s, _, tea = _started(db, True)
    item = session_service.add_item(db, s.id, tea.id, 2, None, user)
    assert not item.from_package and s.total_product_fee == D("20000.00")


def test_session_without_package_has_no_free_items(db):
    user, table = _setup(db)
    beer = make_product(db)
    s = table_service.start_session(db, table.id, user)
    item = session_service.add_item(db, s.id, beer.id, 2, None, user)
    assert not item.from_package and s.total_product_fee == D("40000.00")


def test_free_items_do_not_leak_between_sessions(db):
    user, table = _setup(db)
    beer = make_product(db)
    pkg = make_package(db, items=[(beer.id, 1)])
    first = table_service.start_session(db, table.id, user, package_id=pkg.id)
    session_service.add_item(db, first.id, beer.id, 1, None, user)
    session_service.stop_session(db, first.id, user)
    db.commit()
    second = table_service.start_session(db, table.id, user, package_id=pkg.id)
    item = session_service.add_item(db, second.id, beer.id, 1, None, user)
    assert item.from_package                              # a fresh allowance for the new session


def test_package_with_discount_and_products_totals(db):
    user, table, s, beer, tea = _started(db, True)
    session_service.add_item(db, s.id, beer.id, 3, None, user)      # 2 free + 1 paid (20,000)
    session_service.add_item(db, s.id, tea.id, 1, None, user)       # 10,000
    session_lifecycle.finalize_stop(db, s, table, None, at=s.start_time)
    assert s.total_table_fee == D("80000.00") and s.total_product_fee == D("30000.00")
    assert s.grand_total == D("110000.00")


def test_bill_shows_package_fields_and_free_lines(db):
    user, table, s, beer, _ = _started(db, True, minutes=60)
    session_service.add_item(db, s.id, beer.id, 3, None, user)
    s.start_time = T0
    session_lifecycle.finalize_stop(db, s, table, None, at=T0 + timedelta(minutes=90))
    db.commit()
    bill = session_service.build_bill(s)
    assert bill["package_name"] == "1h Combo" and bill["package_price"] == D("80000.00")
    assert bill["package_minutes"] == 60
    assert bill["duration_minutes"] == 90 and bill["overtime_minutes"] == 30
    assert [i["from_package"] for i in bill["items"]] == [True, False]


def test_bill_of_a_session_without_package_has_null_package_fields(db):
    _, table = _setup(db)
    bill = session_service.build_bill(play(db, table, 30))
    assert bill["package_name"] is None and bill["overtime_minutes"] is None and bill["package_minutes"] is None


def test_old_session_row_without_the_new_columns_values_still_bills(db):
    """Legacy rows: package_snapshot NULL, from_package false."""
    _, table = _setup(db)
    s = play(db, table, 45)
    assert s.package_snapshot is None
    assert all(i.from_package is False for i in s.items)
    assert session_service.build_bill(s)["total_table_fee"] == s.total_table_fee


# ---------------------------------------------------------------- controller event

@pytest.fixture()
def device(db):
    d = BilliardDevice(client_id="c1", device_id="DEV1", name="ctrl", api_key_hash=hash_api_key("secret"))
    db.add(d)
    db.commit()
    return d


def _start_event(table, package_id=None, local="LOCAL-S-1"):
    data = {} if package_id is None else {"package_id": package_id}
    return DeviceEventIn(event_id="e1", event="session_start", device_seq=1, data=data,
                         table_id=table.id, local_session_id=local)


def test_package_start_from_controller_event(db, device):
    _, table = _setup(db)
    beer = make_product(db)
    pkg = make_package(db, items=[(beer.id, 1)])
    res = event_service.ingest(db, device, [_start_event(table, pkg.id)])
    assert res.accepted == ["e1"]
    s = db.execute(select(TableSession)).scalar_one()
    assert s.package_snapshot["package_id"] == pkg.id and s.ends_at is not None


@pytest.mark.parametrize("make", [
    lambda db: make_package(db, active=False).id,        # inactive
    lambda db: make_package(db, client_id="c2").id,      # other club
    lambda db: 99999,                                    # unknown
])
def test_event_with_unusable_package_still_opens_the_session_and_says_so(db, device, make):
    _, table = _setup(db)
    package_id = make(db)
    res = event_service.ingest(db, device, [_start_event(table, package_id)])
    assert res.accepted == ["e1"]                        # the device really played; never lose the session
    s = db.execute(select(TableSession)).scalar_one()
    assert s.package_snapshot is None
    from app.billiard.models import DeviceEvent
    row = db.execute(select(DeviceEvent)).scalar_one()
    assert "package_ignored" in row.payload["reconciled"]


def test_event_without_package_is_unchanged(db, device):
    _, table = _setup(db)
    event_service.ingest(db, device, [_start_event(table)])
    assert db.execute(select(TableSession)).scalar_one().package_snapshot is None


# ---------------------------------------------------------------- HTTP: start, add item, quote

def _http_user(client_id="c1", role="staff"):
    return SimpleNamespace(
        id=1, client_id=client_id, username="u",
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
    beer = make_product(seed)
    pkg = make_package(seed, items=[(beer.id, 1)])
    seed.commit()
    ids = SimpleNamespace(user_id=user.id, table_id=table.id, beer_id=beer.id, package_id=pkg.id)
    seed.close()

    app = FastAPI()
    for r in (table_router, session_router, pricing_router):
        app.include_router(r)

    def _db():
        s = Session()
        try:
            yield s
        finally:
            s.close()

    holder = {"u": _http_user()}
    holder["u"].id = ids.user_id
    app.dependency_overrides[get_db] = _db
    app.dependency_overrides[get_current_user] = lambda: holder["u"]
    c = TestClient(app)
    c.ids, c.holder = ids, holder
    return c


def test_http_start_with_package_then_add_items_then_stop(client):
    i = client.ids
    r = client.post(f"/tables/{i.table_id}/start", json={"package_id": i.package_id})
    assert r.status_code == 200 and r.json()["ends_at"] is not None
    sid = r.json()["session_id"]

    a = client.post(f"/sessions/{sid}/items", json={"product_id": i.beer_id, "quantity": 2})
    assert a.status_code == 201 and a.json()["unit_price"] == "20000.00"      # the paid line is returned
    bill = client.get(f"/sessions/{sid}").json()
    assert [(x["quantity"], x["from_package"]) for x in bill["items"]] == [(1, True), (1, False)]
    assert bill["package_name"] == "1h Combo"

    stopped = client.post(f"/sessions/{sid}/stop").json()
    assert stopped["total_table_fee"] == "80000.00" and stopped["grand_total"] == "100000.00"


def test_http_start_rejects_package_and_planned_minutes_together(client):
    r = client.post(f"/tables/{client.ids.table_id}/start",
                    json={"package_id": client.ids.package_id, "planned_minutes": 30})
    assert r.status_code == 422


def test_http_start_with_unknown_package_is_404(client):
    assert client.post(f"/tables/{client.ids.table_id}/start", json={"package_id": 999}).status_code == 404


def test_quote_with_package_matches_real_bill(client, db=None):
    i = client.ids
    q = client.get("/billiard/pricing-rules/quote",
                   params={"table_id": i.table_id, "minutes": 90, "package_id": i.package_id}).json()
    assert q["package_name"] == "1h Combo" and q["package_minutes"] == 60 and q["overtime_minutes"] == 30
    assert q["fee"] == "130000.00"                       # 80,000 + 30 min at 100,000/h
    plain = client.get("/billiard/pricing-rules/quote", params={"table_id": i.table_id, "minutes": 90}).json()
    assert plain["fee"] == "150000.00" and plain["package_name"] is None


def test_quote_matches_stop_total_for_a_package_session(db):
    from app.billiard.services.billing_service import billing_service
    _, table = _setup(db)
    pkg = make_package(db)
    quote = billing_service.preview_fee(db, table, T0, 90, package=pkg)
    s = play(db, table, 90, pkg)
    assert quote["fee"] == s.total_table_fee


def test_quote_with_inactive_or_foreign_package(client):
    i = client.ids
    assert client.get("/billiard/pricing-rules/quote",
                      params={"table_id": i.table_id, "minutes": 60, "package_id": 999}).status_code == 404
    client.holder["u"] = _http_user("other-club")
    assert client.get("/billiard/pricing-rules/quote",
                      params={"table_id": i.table_id, "minutes": 60, "package_id": i.package_id}).status_code == 404
