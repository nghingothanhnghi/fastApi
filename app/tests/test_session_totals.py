# app/tests/test_session_totals.py
# P0: recompute_totals is the single formula for product fee and grand total.
from decimal import Decimal

from app.tests._billiard_fixtures import *  # noqa: F401,F403
from app.billiard.models import SessionItem, SessionStatus
from app.billiard.services import session_lifecycle
from app.billiard.services.session_service import session_service
from app.billiard.services.table_service import table_service
from app.product.models.product import Product


def _active(db):
    user = make_user(db)
    table = make_table(db)
    session = table_service.start_session(db, table.id, user)
    db.commit()
    return user, table, session


def _item(session, price, qty=1):
    session.items.append(SessionItem(
        product_name="x", quantity=qty, unit_price=Decimal(price), total_price=Decimal(price) * qty,
    ))


def test_recompute_totals_matches_old_formula_with_zero_discount(db):
    _, _, s = _active(db)
    s.total_table_fee = Decimal("50000")
    _item(s, "10000", 2)
    session_lifecycle.recompute_totals(s)
    assert s.total_product_fee == Decimal("20000")
    assert s.grand_total == Decimal("70000")          # table + products, as before


def test_recompute_totals_subtracts_discount(db):
    _, _, s = _active(db)
    s.total_table_fee = Decimal("50000")
    _item(s, "10000", 2)
    s.discount = Decimal("5000")
    session_lifecycle.recompute_totals(s)
    assert s.grand_total == Decimal("65000")


def test_recompute_totals_never_negative(db):
    _, _, s = _active(db)
    s.total_table_fee = Decimal("1000")
    s.discount = Decimal("999999")
    session_lifecycle.recompute_totals(s)
    assert s.grand_total == Decimal("0")


def test_add_item_and_stop_give_same_grand_total_as_before(db):
    user, _, s = _active(db)
    p = Product(name="Beer", base_price=Decimal("25000"))
    db.add(p)
    db.flush()
    session_service.add_item(db, s.id, p.id, 2, None, user)
    assert s.grand_total == Decimal("50000")           # table fee still 0 while playing
    stopped = session_service.stop_session(db, s.id, user)
    assert stopped.status == SessionStatus.COMPLETED
    assert stopped.grand_total == stopped.total_table_fee + Decimal("50000")
