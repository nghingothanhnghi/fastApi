# app/tests/payments_testkit.py
# Shared helpers for the Payments module tests.
#
# The core tests run against a FAKE business (not billiard) to prove the Payments module only
# needs the PayableAdapter contract. Billiard has its own integration tests.
import os
import tempfile
from decimal import Decimal
from typing import Optional

# app.database / app.core.config validate env at import time.
os.environ.setdefault("DATABASE_URL", f"sqlite:///{tempfile.gettempdir()}/payments_test_import.db")
os.environ.setdefault("OPENAI_API_KEY", "test")
os.environ.setdefault("SECRET_KEY", "test")

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base
from app.payments.models import bank_transaction, order, shift  # noqa: F401  (registers payment tables)
from app.payments.models.payment import PaymentTransaction  # noqa: F401
from app.payments.schemas.order import PayOrderRequest
from app.payments.services.order_service import payment_order_service
from app.payments.services.payable_registry import Quote, payable_registry
from app.product.models.product import Product, ProductVariant  # noqa: F401
from app.user.models.role import Role
from app.user.models.user import User
from app.user.models.user_role import UserRole
from app.hydro_system.models.device import HydroDevice  # noqa: F401
from app.hydro_system.models.actuator import HydroActuator  # noqa: F401
from app.hydro_system.models.actuator_log import HydroActuatorLog  # noqa: F401
from app.hydro_system.models.schedule import HydroSchedule  # noqa: F401

CLIENT = "c1"
D = Decimal
FAKE = "fake_bill"


# ------------------------------------------------------------------ fake business

class FakeBill:
    """A business object that is not billiard: just an amount, a tenant and mirrored payment fields."""

    def __init__(self, bill_id: int, client_id: str, total: Decimal, ready: bool):
        self.id, self.client_id, self.total, self.ready = bill_id, client_id, total, ready
        self.state: Optional[str] = "unpaid"
        self.method = self.payment_id = self.payment_reference = self.paid_at = self.paid_by_id = None
        self.order_id = None
        self.applied = 0                                  # how many times Payments mirrored state onto us


class FakePayable:
    source_type = FAKE

    def __init__(self):
        self.bills: dict[int, FakeBill] = {}
        self._seq = 0

    def create(self, total="310000", client_id=CLIENT, ready=True) -> str:
        self._seq += 1
        self.bills[self._seq] = FakeBill(self._seq, client_id, D(total), ready)
        return str(self._seq)

    def load(self, db, source_id, user, *, lock=True):
        bill = self.bills.get(int(source_id)) if str(source_id).isdigit() else None
        if bill is None or (user is not None and not user.is_super_admin() and bill.client_id != user.client_id):
            raise HTTPException(404, "Bill not found")
        return bill

    def check_payable(self, bill):
        if not bill.ready:
            raise HTTPException(409, "Bill is not finished yet")

    def quote(self, bill):
        return Quote(client_id=bill.client_id, currency="VND", total=bill.total,
                     metadata={"fake_bill_id": bill.id})

    def apply_state(self, db, bill, order_):
        bill.order_id, bill.state, bill.method = order_.id, order_.state.value, order_.method
        bill.payment_id, bill.payment_reference = order_.payment_id, order_.payment_reference
        bill.paid_at, bill.paid_by_id = order_.paid_at, order_.paid_by_id
        bill.applied += 1


@pytest.fixture()
def fake():
    adapter = FakePayable()
    payable_registry.register(adapter)
    yield adapter
    payable_registry.unregister(FAKE)


# ------------------------------------------------------------------ database + users

@pytest.fixture()
def engine():
    e = create_engine("sqlite://", poolclass=StaticPool, connect_args={"check_same_thread": False})
    Base.metadata.create_all(e)
    return e


@pytest.fixture()
def db(engine):
    s = sessionmaker(bind=engine, autoflush=False)()
    yield s
    s.close()


def make_user(db, name, role=None, client=CLIENT):
    u = User(client_id=client, username=name, email=f"{name}@x.com", hashed_password="x")
    db.add(u)
    db.flush()
    if role:
        r = db.query(Role).filter_by(name=role).first()
        if not r:
            r = Role(name=role, display_name=role, is_active=True)
            db.add(r)
            db.flush()
        db.add(UserRole(user_id=u.id, role_id=r.id))
    db.commit()
    return u


@pytest.fixture()
def cashier(db):
    return make_user(db, "cashier")


@pytest.fixture()
def manager(db):
    return make_user(db, "boss", role="manager")


# ------------------------------------------------------------------ shortcuts

def pay(db, user, bill_id, **body):
    """-> (order, gateway)"""
    return payment_order_service.pay(db, FAKE, str(bill_id), PayOrderRequest(**body), user)


def view(db, user, bill_id) -> dict:
    return payment_order_service.get_view(db, FAKE, str(bill_id), user)


def events(db, bill_id):
    """Event types of a fake bill's order, oldest first."""
    from app.payments.models.order import PaymentEvent
    order_ = payment_order_service.get_order(db, FAKE, str(bill_id))
    if order_ is None:
        return []
    return [e.event_type for e in db.query(PaymentEvent).filter(PaymentEvent.order_id == order_.id)
            .order_by(PaymentEvent.id)]
