# app/tests/test_cms.py
# CMS module tests: visibility, permissions, validation, scheduling, menus, uploads, slugs.
# Uses an in-memory SQLite DB and a header-driven fake auth (X-Test-User: <key>).
import io
from datetime import datetime, timedelta, timezone

import pytest
from fastapi import Depends, FastAPI, Header, HTTPException
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import app.init_db  # noqa: F401  (registers every model so mappers configure)
from app.database import Base, get_db
from app.cms.routes import cms_router
from app.cms.services.post_service import post_service
from app.cms.models.post import CmsPost, PostStatus
from app.cms.utils.slugify import slugify
from app.user.models.user import User
from app.user.utils import token as token_utils


class FakeUser:
    def __init__(self, id, *roles):
        self.id = id
        self._roles = set(roles)
        self.is_active = True

    def has_role(self, role):
        return getattr(role, "value", role) in self._roles


USERS = {
    "author": FakeUser(1, "user"),
    "other": FakeUser(2, "user"),
    "mod": FakeUser(3, "moderator"),
    "admin": FakeUser(4, "admin"),
}
AUTH = {k: {"X-Test-User": k} for k in USERS}

PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 32


@pytest.fixture()
def client():
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine, autoflush=False)

    with Session() as s:
        for key, u in USERS.items():
            s.add(User(id=u.id, client_id="c", username=key, email=f"{key}@x.io", hashed_password="x"))
        s.commit()

    app = FastAPI()
    app.include_router(cms_router)

    def _db():
        db = Session()
        try:
            yield db
        finally:
            db.close()

    def _user(x_test_user: str = Header(None)):
        if x_test_user not in USERS:
            raise HTTPException(401, "Not authenticated")
        return USERS[x_test_user]

    def _user_optional(x_test_user: str = Header(None)):
        return USERS.get(x_test_user)

    app.dependency_overrides[get_db] = _db
    app.dependency_overrides[token_utils.get_current_user] = _user
    app.dependency_overrides[token_utils.get_current_user_optional] = _user_optional

    c = TestClient(app)
    c.session_factory = Session
    return c


def _post(client, who="author", **kw):
    body = {"title": "Hello World", "content": "x", **kw}
    r = client.post("/cms/posts", json=body, headers=AUTH[who])
    assert r.status_code == 201, r.text
    return r.json()


# ── slugs ────────────────────────────────────────────────────────────────
def test_slugify_vietnamese_d():
    assert slugify("Hệ thống thủy canh đẹp") == "he-thong-thuy-canh-dep"
    assert slugify("Đà Lạt") == "da-lat"


def test_post_slug_unique(client):
    a = _post(client)
    b = _post(client)
    assert a["slug"] == "hello-world" and b["slug"] == "hello-world-2"


# ── visibility ───────────────────────────────────────────────────────────
def test_draft_hidden_from_public(client):
    draft = _post(client)
    pub = _post(client, title="Live", status="published")

    assert client.get(f"/cms/posts/{draft['id']}").status_code == 404
    assert client.get(f"/cms/posts/slug/{draft['slug']}").status_code == 404
    assert client.get(f"/cms/posts/{draft['id']}", headers=AUTH["other"]).status_code == 404
    assert client.get(f"/cms/posts/{pub['id']}").status_code == 200

    r = client.get("/cms/posts")
    assert [p["id"] for p in r.json()["results"]] == [pub["id"]]
    assert client.get("/cms/posts?status=draft").status_code == 403


def test_author_and_editor_see_drafts(client):
    draft = _post(client)
    assert client.get(f"/cms/posts/{draft['id']}", headers=AUTH["author"]).status_code == 200
    assert client.get(f"/cms/posts/{draft['id']}", headers=AUTH["mod"]).status_code == 200
    r = client.get("/cms/posts?status=draft", headers=AUTH["mod"])
    assert r.status_code == 200 and r.json()["total"] == 1
    r = client.get(f"/cms/posts?author_id=1&status=draft", headers=AUTH["author"])
    assert r.status_code == 200 and r.json()["total"] == 1


def test_view_count_only_for_published(client):
    pub = _post(client, status="published")
    client.get(f"/cms/posts/slug/{pub['slug']}")
    client.get(f"/cms/posts/slug/{pub['slug']}?track_view=false")
    assert client.get(f"/cms/posts/{pub['id']}").json()["view_count"] == 1


def test_only_owner_or_editor_can_modify(client):
    p = _post(client)
    r = client.put(f"/cms/posts/{p['id']}", json={"title": "x"}, headers=AUTH["other"])
    assert r.status_code == 403
    assert client.put(f"/cms/posts/{p['id']}", json={"title": "x"}, headers=AUTH["mod"]).status_code == 200


# ── reference validation ─────────────────────────────────────────────────
def test_post_invalid_references_are_400(client):
    for body in ({"category_id": 999}, {"featured_image_id": 999}, {"tag_ids": [999]}):
        r = client.post("/cms/posts", json={"title": "t", **body}, headers=AUTH["author"])
        assert r.status_code == 400, (body, r.text)
    p = _post(client)
    r = client.put(f"/cms/posts/{p['id']}", json={"category_id": 999}, headers=AUTH["author"])
    assert r.status_code == 400


# ── scheduling ───────────────────────────────────────────────────────────
def _future(minutes=60):
    return (datetime.now(timezone.utc) + timedelta(minutes=minutes)).isoformat()


def test_schedule_validation(client):
    past = (datetime.now(timezone.utc) - timedelta(minutes=5)).isoformat()
    h = AUTH["author"]
    assert client.post("/cms/posts", json={"title": "t", "status": "scheduled"}, headers=h).status_code == 422
    assert client.post("/cms/posts", json={"title": "t", "status": "scheduled", "scheduled_at": past}, headers=h).status_code == 400
    p = _post(client)
    assert client.post(f"/cms/posts/{p['id']}/schedule", json={"scheduled_at": past}, headers=h).status_code == 400
    # update path must enforce the same rule
    r = client.put(f"/cms/posts/{p['id']}", json={"status": "scheduled", "scheduled_at": past}, headers=h)
    assert r.status_code == 400
    r = client.post(f"/cms/posts/{p['id']}/schedule", json={"scheduled_at": _future()}, headers=h)
    assert r.status_code == 200 and r.json()["status"] == "scheduled"


def test_job_publishes_only_due_posts(client):
    due = _post(client, title="due")
    later = _post(client, title="later")
    client.post(f"/cms/posts/{later['id']}/schedule", json={"scheduled_at": _future(120)}, headers=AUTH["author"])
    client.post(f"/cms/posts/{due['id']}/schedule", json={"scheduled_at": _future(1)}, headers=AUTH["author"])

    with client.session_factory() as db:
        db.query(CmsPost).filter(CmsPost.id == due["id"]).update(
            {CmsPost.scheduled_at: datetime.now(timezone.utc) - timedelta(seconds=1)}
        )
        db.commit()
        assert post_service.publish_due_scheduled_posts(db) == 1
        assert db.query(CmsPost).get(due["id"]).status == PostStatus.published
        assert db.query(CmsPost).get(due["id"]).published_at is not None
        assert db.query(CmsPost).get(later["id"]).status == PostStatus.scheduled


# ── categories ───────────────────────────────────────────────────────────
def test_category_parent_rules(client):
    h = AUTH["mod"]
    a = client.post("/cms/categories", json={"name": "A"}, headers=h).json()
    b = client.post("/cms/categories", json={"name": "B", "parent_id": a["id"]}, headers=h).json()
    assert client.post("/cms/categories", json={"name": "X", "parent_id": 999}, headers=h).status_code == 400
    assert client.put(f"/cms/categories/{a['id']}", json={"parent_id": a["id"]}, headers=h).status_code == 400
    assert client.put(f"/cms/categories/{a['id']}", json={"parent_id": b["id"]}, headers=h).status_code == 400
    assert client.put(f"/cms/categories/{b['id']}", json={"parent_id": None}, headers=h).status_code == 200


# ── tags ─────────────────────────────────────────────────────────────────
def test_duplicate_tag_is_409(client):
    h = AUTH["mod"]
    assert client.post("/cms/tags", json={"name": "Hydro"}, headers=h).status_code == 201
    assert client.post("/cms/tags", json={"name": "hydro"}, headers=h).status_code == 409


# ── media ────────────────────────────────────────────────────────────────
@pytest.fixture()
def media_dir(tmp_path, monkeypatch):
    from app.cms.services import media_service as ms
    monkeypatch.setattr(ms, "CMS_MEDIA_DIR", str(tmp_path))
    return tmp_path


def _upload(client, who, name="a.png", data=PNG):
    return client.post("/cms/media/upload", files={"file": (name, io.BytesIO(data), "image/png")}, headers=AUTH[who])


def test_upload_validation(client, media_dir):
    assert _upload(client, "author").status_code == 201
    assert _upload(client, "author", "evil.png", b"<script>alert(1)</script>").status_code == 400  # wrong magic bytes
    assert _upload(client, "author", "x.svg", b"<svg/>").status_code == 400                      # svg not allowed
    assert _upload(client, "author", "x.exe", b"MZ").status_code == 400
    assert client.post("/cms/media/upload", files={"file": ("a.png", io.BytesIO(PNG))}).status_code == 401


def test_media_permissions_and_in_use_protection(client, media_dir):
    m = _upload(client, "author").json()
    assert client.patch(f"/cms/media/{m['id']}", data={"alt_text": "hi"}, headers=AUTH["other"]).status_code == 403
    assert client.delete(f"/cms/media/{m['id']}", headers=AUTH["other"]).status_code == 403
    assert client.patch(f"/cms/media/{m['id']}", data={"alt_text": "hi"}, headers=AUTH["author"]).status_code == 200

    p = _post(client, featured_image_id=m["id"])
    assert client.delete(f"/cms/media/{m['id']}", headers=AUTH["author"]).status_code == 409
    client.put(f"/cms/posts/{p['id']}", json={"featured_image_id": None}, headers=AUTH["author"])
    assert client.delete(f"/cms/media/{m['id']}", headers=AUTH["mod"]).status_code == 200
    assert list(media_dir.iterdir()) == []


# ── menus ────────────────────────────────────────────────────────────────
def test_menu_tree_reorder_and_cycles(client):
    h = AUTH["mod"]
    menu = client.post("/cms/menus", json={"name": "Header", "location": "header"}, headers=h).json()
    mid = menu["id"]
    a = client.post(f"/cms/menus/{mid}/items", json={"label": "A", "url": "/a"}, headers=h).json()
    b = client.post(f"/cms/menus/{mid}/items", json={"label": "B", "url": "/b", "parent_id": a["id"]}, headers=h).json()

    tree = client.get("/cms/menus/location/header").json()
    assert "_sa_instance_state" not in tree
    assert tree["items"][0]["children"][0]["id"] == b["id"]
    assert client.get("/cms/menus/location/nope").status_code == 404

    # cycle via update and via reorder
    assert client.put(f"/cms/menus/items/{a['id']}", json={"parent_id": b["id"]}, headers=h).status_code == 400
    body = {"items": [{"id": a["id"], "parent_id": b["id"], "order": 0}, {"id": b["id"], "parent_id": a["id"], "order": 1}]}
    assert client.post(f"/cms/menus/{mid}/items/reorder", json=body, headers=h).status_code == 400

    # unknown menu is a 404, not a 500
    assert client.post("/cms/menus/999/items/reorder", json={"items": []}, headers=h).status_code == 404

    ok = {"items": [{"id": b["id"], "parent_id": None, "order": 0}, {"id": a["id"], "parent_id": None, "order": 1}]}
    r = client.post(f"/cms/menus/{mid}/items/reorder", json=ok, headers=h)
    assert r.status_code == 200 and [i["id"] for i in r.json()] == [b["id"], a["id"]]


# ── P1: menu resolution, response models, limits ─────────────────────────
def test_menu_urls_only_link_published_posts_and_avoid_n_plus_1(client):
    from sqlalchemy import event

    h = AUTH["mod"]
    cat = client.post("/cms/categories", json={"name": "News"}, headers=h).json()
    live = _post(client, title="Live", status="published")
    draft = _post(client, title="Draft")
    mid = client.post("/cms/menus", json={"name": "Main", "location": "main"}, headers=h).json()["id"]

    def add(body):
        r = client.post(f"/cms/menus/{mid}/items", json=body, headers=h)
        assert r.status_code == 201, r.text
        return r.json()

    c = add({"label": "C", "target_type": "category", "target_id": cat["id"]})
    assert c["resolved_url"] == "/categories/news"
    add({"label": "L", "target_type": "post", "target_id": live["id"]})
    add({"label": "D", "target_type": "post", "target_id": draft["id"]})
    for i in range(10):
        add({"label": f"X{i}", "url": f"/x{i}"})

    engine = client.session_factory.kw["bind"]
    count = {"n": 0}
    listener = lambda *a, **k: count.__setitem__("n", count["n"] + 1)
    event.listen(engine, "before_cursor_execute", listener)
    try:
        r = client.get("/cms/menus/location/main")
    finally:
        event.remove(engine, "before_cursor_execute", listener)

    items = {i["label"]: i for i in r.json()["items"]}
    assert items["C"]["resolved_url"] == "/categories/news"
    assert items["L"]["resolved_url"] == f"/posts/{live['slug']}"
    assert items["D"]["resolved_url"] is None  # unpublished -> no link
    assert items["X3"]["resolved_url"] == "/x3"
    assert count["n"] <= 5, f"too many queries for a 13-item menu: {count['n']}"


def test_menu_list_is_typed_without_items(client):
    h = AUTH["mod"]
    client.post("/cms/menus", json={"name": "Footer", "location": "footer"}, headers=h)
    r = client.get("/cms/menus")
    assert r.status_code == 200
    assert set(r.json()[0]) == {"id", "name", "slug", "location", "created_at", "updated_at"}


def test_page_size_limits_come_from_config(client):
    from app.cms.config import MAX_PAGE_SIZE, MAX_MEDIA_LIMIT
    assert client.get(f"/cms/posts?page_size={MAX_PAGE_SIZE + 1}").status_code == 422
    assert client.get(f"/cms/media?limit={MAX_MEDIA_LIMIT + 1}").status_code == 422
    assert client.get(f"/cms/posts?page_size={MAX_PAGE_SIZE}").status_code == 200
