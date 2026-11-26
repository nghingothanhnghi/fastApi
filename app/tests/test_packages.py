# app/tests/test_packages.py
# Roadmap item E: package CRUD (service level + HTTP).
from types import SimpleNamespace

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
from pydantic import ValidationError
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.tests._billiard_fixtures import *  # noqa: F401,F403
from app.billiard.models import BilliardPackage, BilliardPackageItem
from app.billiard.routes.package_router import router
from app.billiard.schemas.package import PackageCreate, PackageItemIn, PackageUpdate
from app.billiard.services.package_service import package_service
from app.database import Base, get_db
from app.product.models.product import Product
from app.user.utils.token import get_current_user


def make_product(db, name="Beer", price=20000, active=True):
    p = Product(name=name, base_price=price, is_active=active)
    db.add(p)
    db.flush()
    return p


def _create(db, user, name="2h Combo", minutes=120, price="150000", items=()):
    data = PackageCreate(name=name, duration_minutes=minutes, price=Decimal(price), items=list(items))
    pkg = package_service.create_package(db, data, user)
    db.commit()
    return pkg


# ---------------------------------------------------------------- service

def test_create_package_with_items(db):
    user = make_user(db)
    beer = make_product(db)
    pkg = _create(db, user, items=[PackageItemIn(product_id=beer.id, included_quantity=2)])
    assert pkg.client_id == "c1" and pkg.is_active and pkg.price == Decimal("150000")
    out = package_service.to_out(db, pkg)
    assert out.items[0].product_name == "Beer" and out.items[0].included_quantity == 2


def test_duplicate_name_in_same_club_is_409(db):
    user = make_user(db)
    _create(db, user)
    with pytest.raises(HTTPException) as e:
        _create(db, user)
    assert e.value.status_code == 409


def test_same_name_in_other_club_is_ok(db):
    a, b = make_user(db, "c1", "a"), make_user(db, "c2", "b")
    _create(db, a)
    assert _create(db, b).client_id == "c2"


def test_name_is_trimmed_and_blank_rejected():
    assert PackageCreate(name="  Combo ", duration_minutes=60, price=Decimal("1")).name == "Combo"
    with pytest.raises(ValidationError):
        PackageCreate(name="   ", duration_minutes=60, price=Decimal("1"))


@pytest.mark.parametrize("kwargs", [
    dict(duration_minutes=0, price=Decimal("1")),
    dict(duration_minutes=1441, price=Decimal("1")),
    dict(duration_minutes=60, price=Decimal("-1")),
    dict(duration_minutes=60, price=Decimal("1.234")),
    dict(duration_minutes=60, price=Decimal("1"), items=[{"product_id": 1, "included_quantity": 0}]),
])
def test_duration_and_price_validation(kwargs):
    with pytest.raises(ValidationError):
        PackageCreate(name="x", **kwargs)


def test_zero_price_is_allowed():
    assert PackageCreate(name="Free", duration_minutes=10, price=Decimal("0")).price == 0


def test_duplicate_product_in_items_is_rejected():
    items = [{"product_id": 1, "included_quantity": 1}, {"product_id": 1, "included_quantity": 2}]
    with pytest.raises(ValidationError):
        PackageCreate(name="x", duration_minutes=60, price=Decimal("1"), items=items)
    with pytest.raises(ValidationError):
        PackageUpdate(items=items)


def test_unknown_product_is_400(db):
    user = make_user(db)
    with pytest.raises(HTTPException) as e:
        _create(db, user, items=[PackageItemIn(product_id=999, included_quantity=1)])
    assert e.value.status_code == 400


def test_inactive_product_is_400(db):
    user = make_user(db)
    off = make_product(db, active=False)
    with pytest.raises(HTTPException) as e:
        _create(db, user, items=[PackageItemIn(product_id=off.id, included_quantity=1)])
    assert e.value.status_code == 400 and "not available" in e.value.detail


def test_update_replaces_items(db):
    user = make_user(db)
    beer, tea = make_product(db, "Beer"), make_product(db, "Tea")
    pkg = _create(db, user, items=[PackageItemIn(product_id=beer.id, included_quantity=2)])
    package_service.update_package(
        db, pkg.id, PackageUpdate(items=[PackageItemIn(product_id=tea.id, included_quantity=1),
                                         PackageItemIn(product_id=beer.id, included_quantity=3)]), user)
    db.commit()
    got = {(i.product_id, i.included_quantity) for i in db.get(BilliardPackage, pkg.id).items}
    assert got == {(tea.id, 1), (beer.id, 3)}
    assert db.query(BilliardPackageItem).count() == 2      # old rows are gone, not orphaned


def test_update_without_items_keeps_them_and_empty_list_clears_them(db):
    user = make_user(db)
    beer = make_product(db)
    pkg = _create(db, user, items=[PackageItemIn(product_id=beer.id, included_quantity=2)])
    package_service.update_package(db, pkg.id, PackageUpdate(price=Decimal("99")), user)
    db.commit()
    db.refresh(pkg)
    assert pkg.price == Decimal("99") and len(pkg.items) == 1
    package_service.update_package(db, pkg.id, PackageUpdate(items=[]), user)
    db.commit()
    db.refresh(pkg)
    assert pkg.items == []


def test_update_to_taken_name_is_409_but_own_name_is_ok(db):
    user = make_user(db)
    _create(db, user, name="A")
    b = _create(db, user, name="B")
    with pytest.raises(HTTPException) as e:
        package_service.update_package(db, b.id, PackageUpdate(name="A"), user)
    assert e.value.status_code == 409
    assert package_service.update_package(db, b.id, PackageUpdate(name="B", price=Decimal("5")), user).price == 5


def test_deactivate_hides_from_default_list_but_keeps_row(db):
    user = make_user(db)
    pkg = _create(db, user)
    package_service.deactivate_package(db, pkg.id, user)
    package_service.deactivate_package(db, pkg.id, user)      # twice is fine
    db.commit()
    assert package_service.list_packages(db, user) == []
    assert [p.id for p in package_service.list_packages(db, user, include_inactive=True)] == [pkg.id]
    assert package_service.get_package(db, pkg.id, user).is_active is False


def test_reactivate_with_update(db):
    user = make_user(db)
    pkg = _create(db, user)
    package_service.deactivate_package(db, pkg.id, user)
    package_service.update_package(db, pkg.id, PackageUpdate(is_active=True), user)
    assert [p.id for p in package_service.list_packages(db, user)] == [pkg.id]


def test_list_is_tenant_scoped_and_other_tenant_gets_404(db):
    a, b = make_user(db, "c1", "a"), make_user(db, "c2", "b")
    pkg = _create(db, a)
    assert package_service.list_packages(db, b) == []
    for call in (lambda: package_service.get_package(db, pkg.id, b),
                 lambda: package_service.update_package(db, pkg.id, PackageUpdate(price=Decimal("1")), b),
                 lambda: package_service.deactivate_package(db, pkg.id, b)):
        with pytest.raises(HTTPException) as e:
            call()
        assert e.value.status_code == 404


def test_unknown_package_is_404(db):
    with pytest.raises(HTTPException) as e:
        package_service.get_package(db, 9999, make_user(db))
    assert e.value.status_code == 404


# ---------------------------------------------------------------- HTTP

def _http_user(role="manager", client_id="c1"):
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
    beer = make_product(seed)
    seed.commit()
    beer_id = beer.id
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
    c.beer_id, c.holder = beer_id, holder
    return c


def _body(client, **over):
    body = {"name": "2h Combo", "duration_minutes": 120, "price": "150000",
            "items": [{"product_id": client.beer_id, "included_quantity": 2}]}
    body.update(over)
    return body


def test_http_crud_roundtrip(client):
    r = client.post("/billiard/packages", json=_body(client))
    assert r.status_code == 201
    pid = r.json()["id"]
    assert r.json()["items"][0]["product_name"] == "Beer"

    assert client.get(f"/billiard/packages/{pid}").json()["name"] == "2h Combo"
    assert [p["id"] for p in client.get("/billiard/packages").json()] == [pid]

    r = client.put(f"/billiard/packages/{pid}", json={"price": "120000", "items": []})
    assert r.status_code == 200 and r.json()["price"] == "120000.00" and r.json()["items"] == []

    r = client.delete(f"/billiard/packages/{pid}")
    assert r.status_code == 200 and r.json()["is_active"] is False
    assert client.get("/billiard/packages").json() == []
    assert len(client.get("/billiard/packages?include_inactive=true").json()) == 1


def test_http_validation_is_422_and_conflicts_are_409_400(client):
    assert client.post("/billiard/packages", json=_body(client, duration_minutes=0)).status_code == 422
    assert client.post("/billiard/packages", json=_body(client, price="-1")).status_code == 422
    dup = [{"product_id": client.beer_id, "included_quantity": 1}] * 2
    assert client.post("/billiard/packages", json=_body(client, items=dup)).status_code == 422
    assert client.post("/billiard/packages", json=_body(client)).status_code == 201
    assert client.post("/billiard/packages", json=_body(client)).status_code == 409
    bad = [{"product_id": 12345, "included_quantity": 1}]
    assert client.post("/billiard/packages", json=_body(client, name="Other", items=bad)).status_code == 400


def test_package_endpoints_manager_only_for_writes(client):
    pid = client.post("/billiard/packages", json=_body(client)).json()["id"]
    client.holder["u"] = _http_user("staff")
    assert client.get("/billiard/packages").status_code == 200
    assert client.get(f"/billiard/packages/{pid}").status_code == 200
    assert client.post("/billiard/packages", json=_body(client, name="x")).status_code == 403
    assert client.put(f"/billiard/packages/{pid}", json={"price": "1"}).status_code == 403
    assert client.delete(f"/billiard/packages/{pid}").status_code == 403


def test_http_other_tenant_404_and_empty_list(client):
    pid = client.post("/billiard/packages", json=_body(client)).json()["id"]
    client.holder["u"] = _http_user(client_id="other-club")
    assert client.get("/billiard/packages").json() == []
    assert client.get(f"/billiard/packages/{pid}").status_code == 404
    assert client.put(f"/billiard/packages/{pid}", json={"price": "1"}).status_code == 404
    assert client.delete(f"/billiard/packages/{pid}").status_code == 404
