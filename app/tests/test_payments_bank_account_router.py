from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

# NOTE: same imports as bank_account_router.py
from app.tests import _load_models  # noqa: F401  (registers every model)
from app.database import Base, get_db
from app.user.utils.token import get_current_user
from app.payments.models.bank_account import PaymentBankAccount  # noqa: F401
from app.payments.routes.bank_account_router import router
from app.tests.test_payments_bank_qr_parser import make_qr

def _user(role="manager", uid=1):
    # same surface as app.user.models.user.User that payments.utils.permissions.is_manager uses
    return SimpleNamespace(id=uid, client_id=1, is_admin=lambda: False, has_role=lambda r: r == role)


USER = {"u": _user()}


@pytest.fixture()
def client():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    app = FastAPI()
    app.include_router(router)

    def _db():
        s = Session()
        try:
            yield s
        finally:
            s.close()

    app.dependency_overrides[get_db] = _db
    app.dependency_overrides[get_current_user] = lambda: USER["u"]
    USER["u"] = _user()
    return TestClient(app)


PAYLOAD = {"bank_bin": "970436", "account_no": "0123456789", "account_name": "CLUB A"}


def test_create_and_current(client):
    assert client.get("/payments/bank-accounts/current").json() is None
    r = client.post("/payments/bank-accounts", json=PAYLOAD)
    assert r.status_code == 201
    assert client.get("/payments/bank-accounts/current").json()["account_no"] == "0123456789"


def test_staff_cannot_change_accounts(client):
    USER["u"] = _user("staff", 2)
    assert client.post("/payments/bank-accounts", json=PAYLOAD).status_code == 403


def test_invalid_bin_is_422(client):
    assert client.post("/payments/bank-accounts", json={**PAYLOAD, "bank_bin": "12"}).status_code == 422


def test_parse_qr_upload_roundtrip(client, tmp_path):
    cv2 = pytest.importorskip("cv2")
    np = pytest.importorskip("numpy")
    enc = cv2.QRCodeEncoder.create()
    img = enc.encode(make_qr(amount=1000, memo="PAY1L1"))
    img = cv2.resize(img, None, fx=6, fy=6, interpolation=cv2.INTER_NEAREST)
    img = cv2.copyMakeBorder(img, 40, 40, 40, 40, cv2.BORDER_CONSTANT, value=255)
    ok, buf = cv2.imencode(".png", img)
    r = client.post("/payments/bank-accounts/parse-qr", files={"file": ("qr.png", buf.tobytes(), "image/png")})
    assert r.status_code == 200, r.text
    assert r.json()["bank_bin"] == "970436" and r.json()["account_no"] == "0123456789"


def test_parse_qr_rejects_non_image(client):
    r = client.post("/payments/bank-accounts/parse-qr", files={"file": ("x.png", b"not an image", "image/png")})
    assert r.status_code in (422, 501)    
