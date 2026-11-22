import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

# NOTE: same Base import as the models
from app.tests import _load_models  # noqa: F401  (registers every model)
from app.database import Base
from app.payments.models.bank_account import PaymentBankAccount  # noqa: F401
from app.payments.schemas.bank_account import BankAccountCreate, BankAccountRename
from app.payments.services.bank_account_service import bank_account_service as svc


@pytest.fixture()
def db():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    s = sessionmaker(bind=engine)()
    yield s
    s.close()


def body(no="0123456789", bin_="970436"):
    return BankAccountCreate(bank_bin=bin_, account_no=no, account_name="CLUB A")


def test_create_first_account(db):
    acc = svc.create(db, 1, body(), actor_id=9)
    assert acc.is_active and svc.get_active(db, 1).id == acc.id


def test_new_account_replaces_old_and_keeps_history(db):
    a = svc.create(db, 1, body("1111"), 9)
    b = svc.create(db, 1, body("2222"), 9)
    assert svc.get_active(db, 1).id == b.id
    assert a.is_active is False
    assert len(svc.list_accounts(db, 1)) == 2
    assert [e.event_type for e in svc.list_events(db, 1)] == ["account_replaced", "account_created"]


def test_same_account_in_other_club_is_409(db):
    svc.create(db, 1, body(), 9)
    with pytest.raises(HTTPException) as e:
        svc.create(db, 2, body(), 9)
    assert e.value.status_code == 409


def test_clubs_are_isolated(db):
    svc.create(db, 1, body("1111"), 9)
    assert svc.get_active(db, 2) is None
    a = svc.get_active(db, 1)
    with pytest.raises(HTTPException) as e:
        svc.rename(db, 2, a.id, BankAccountRename(account_name="HACK"), 9)
    assert e.value.status_code == 404


def test_deactivate_then_none_active(db):
    a = svc.create(db, 1, body(), 9)
    svc.deactivate(db, 1, a.id, 9)
    assert svc.get_active(db, 1) is None


def test_old_account_number_can_be_reused_after_deactivation(db):
    a = svc.create(db, 1, body(), 9)
    svc.deactivate(db, 1, a.id, 9)
    assert svc.create(db, 2, body(), 9).client_id == 2