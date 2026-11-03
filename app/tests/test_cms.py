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


# ── HTML sanitization ────────────────────────────────────────────────────
from app.cms.utils.sanitize import sanitize_html

XSS_PAYLOADS = [
    "<script>alert(1)</script>",
    '<img src=x onerror="alert(1)">',
    '<a href="javascript:alert(1)">x</a>',
    '<a href="JaVaScRiPt:alert(1)">x</a>',
    '<img src="data:text/html;base64,PHNjcmlwdD4=">',
    '<iframe src="https://evil.example"></iframe>',
    '<svg onload=alert(1)></svg>',
    '<p style="background:url(javascript:alert(1))">x</p>',
    '<form action="/x"><input name=a></form>',
    '<object data="x"></object><embed src="x">',
    '<div onclick="alert(1)">x</div>',
    "<style>body{display:none}</style>",
]


@pytest.mark.parametrize("payload", XSS_PAYLOADS)
def test_sanitize_removes_dangerous_markup(payload):
    out = sanitize_html(payload).lower()
    for bad in ("<script", "onerror", "onload", "onclick", "javascript:", "data:", "<iframe",
                "<svg", "<form", "<object", "<embed", "<style", "style="):
        assert bad not in out, (payload, out)


def test_sanitize_keeps_legit_markup_and_hardens_links():
    html = (
        '<h2 id="intro">Title</h2><p class="lead">Hi <strong>there</strong> '
        '<a href="https://example.com" target="_blank">link</a></p>'
        '<img src="/static/cms_media/a.png" alt="pic" width="10">'
        '<table><tr><td colspan="2">c</td></tr></table><pre><code>x &lt; y</code></pre>'
    )
    out = sanitize_html(html)
    for keep in ("<h2", "<strong>", 'href="https://example.com"', "<table>", 'colspan="2"',
                 'src="/static/cms_media/a.png"', 'alt="pic"', "<pre><code>"):
        assert keep in out, (keep, out)
    assert 'rel="noopener noreferrer"' in out
    assert 'href="mailto:a@b.io"' in sanitize_html('<a href="mailto:a@b.io">m</a>')


def test_sanitize_is_idempotent_and_handles_none():
    once = sanitize_html("".join(XSS_PAYLOADS) + "<p>ok</p>")
    assert sanitize_html(once) == once
    assert sanitize_html(None) is None and sanitize_html("") == ""


def test_post_content_sanitized_on_create_and_update(client):
    h = AUTH["author"]
    p = _post(client, status="published", content='<p>hi</p><script>alert(1)</script><img src=x onerror=alert(1)>')
    assert "<script" not in p["content"] and "onerror" not in p["content"] and "<p>hi</p>" in p["content"]

    r = client.put(f"/cms/posts/{p['id']}", json={"content": '<a href="javascript:alert(1)">x</a>'}, headers=h)
    assert r.status_code == 200 and "javascript:" not in r.json()["content"]
    # fetched back from storage it is still clean
    assert "javascript:" not in client.get(f"/cms/posts/{p['id']}").json()["content"]
    # updating other fields leaves content untouched
    r = client.put(f"/cms/posts/{p['id']}", json={"title": "New"}, headers=h)
    assert r.json()["content"] == client.get(f"/cms/posts/{p['id']}").json()["content"]


def test_backfill_cleans_existing_rows(client):
    p = _post(client, status="published", content="<p>ok</p>")
    with client.session_factory() as db:
        db.query(CmsPost).filter(CmsPost.id == p["id"]).update({CmsPost.content: "<p>ok</p><script>x()</script>"})
        db.commit()
        assert post_service.sanitize_all_posts(db) == 1
        assert post_service.sanitize_all_posts(db) == 0  # idempotent
    assert "<script" not in client.get(f"/cms/posts/{p['id']}").json()["content"]


# ── slug races (check-then-insert) ───────────────────────────────────────
def _force_first_slug(monkeypatch, service, slug):
    """Make the service's FIRST slug pick return an already-taken slug, as if another request
    grabbed it between our existence check and our commit. Later picks behave normally."""
    real = service._unique_slug
    calls = {"n": 0}

    def stub(*args, **kwargs):
        calls["n"] += 1
        return slug if calls["n"] == 1 else real(*args, **kwargs)

    monkeypatch.setattr(service, "_unique_slug", stub)
    return calls


def test_post_create_retries_on_slug_race(client, monkeypatch):
    first = _post(client, title="Alpha")
    calls = _force_first_slug(monkeypatch, post_service, first["slug"])
    second = _post(client, title="Alpha")  # would be a 500 without the retry
    assert second["slug"] == "alpha-2" and calls["n"] == 2
    assert second["id"] != first["id"]


def test_post_update_retries_on_slug_race(client, monkeypatch):
    a = _post(client, title="Alpha")
    b = _post(client, title="Beta", content="<p>keep</p>")
    _force_first_slug(monkeypatch, post_service, a["slug"])
    r = client.put(f"/cms/posts/{b['id']}", json={"slug": "alpha", "title": "Beta 2"}, headers=AUTH["author"])
    assert r.status_code == 200, r.text
    assert r.json()["slug"] == "alpha-2" and r.json()["title"] == "Beta 2"  # edits survive the retry


def test_category_menu_tag_retry_on_slug_race(client, monkeypatch):
    from app.cms.services.category_service import category_service
    from app.cms.services.menu_service import menu_service
    from app.cms.services.tag_service import tag_service

    h = AUTH["mod"]
    cat = client.post("/cms/categories", json={"name": "News"}, headers=h).json()
    _force_first_slug(monkeypatch, category_service, cat["slug"])
    assert client.post("/cms/categories", json={"name": "News"}, headers=h).json()["slug"] == "news-2"

    m = client.post("/cms/menus", json={"name": "Main"}, headers=h).json()
    _force_first_slug(monkeypatch, menu_service, m["slug"])
    assert client.post("/cms/menus", json={"name": "Main"}, headers=h).json()["slug"] == "main-2"

    t = client.post("/cms/tags", json={"name": "Hydro"}, headers=h).json()
    _force_first_slug(monkeypatch, tag_service, t["slug"])
    r = client.post("/cms/tags", json={"name": "Hydro Ponics", "slug": "hydro"}, headers=h)
    assert r.status_code == 201 and r.json()["slug"] == "hydro-2"


def test_retry_helper_conflict_mapping():
    from sqlalchemy.exc import IntegrityError
    from app.cms.utils.slugify import run_with_slug_retry

    class FakeDb:
        rollbacks = 0
        def rollback(self): self.rollbacks += 1

    def boom(msg):
        return IntegrityError("stmt", {}, Exception(msg))

    # non-slug violation -> immediate 409, no retries
    db, n = FakeDb(), {"n": 0}
    def other():
        n["n"] += 1
        raise boom("UNIQUE constraint failed: cms_tags.name")
    with pytest.raises(HTTPException) as e:
        run_with_slug_retry(db, other)
    assert e.value.status_code == 409 and n["n"] == 1 and db.rollbacks == 1

    # persistent slug conflict -> gives up after `attempts` with 409
    db, n = FakeDb(), {"n": 0}
    def always():
        n["n"] += 1
        raise boom("UNIQUE constraint failed: cms_posts.slug")
    with pytest.raises(HTTPException) as e:
        run_with_slug_retry(db, always, attempts=3)
    assert e.value.status_code == 409 and n["n"] == 3

    # succeeds on the 2nd try
    db, n = FakeDb(), {"n": 0}
    def flaky():
        n["n"] += 1
        if n["n"] == 1:
            raise boom('duplicate key value violates unique constraint "ix_cms_posts_slug"')
        return "ok"
    assert run_with_slug_retry(db, flaky) == "ok" and n["n"] == 2


# ── delete rules: categories ─────────────────────────────────────────────
def _cat(client, name, parent_id=None):
    r = client.post("/cms/categories", json={"name": name, "parent_id": parent_id}, headers=AUTH["mod"])
    assert r.status_code == 201, r.text
    return r.json()


def _cat_of(client, cid):
    return client.get(f"/cms/categories/{cid}").json()


def test_delete_category_promotes_children_and_posts_to_parent(client):
    root = _cat(client, "Root")
    mid = _cat(client, "Mid", root["id"])
    leaf = _cat(client, "Leaf", mid["id"])
    p_mid = _post(client, status="published", category_id=mid["id"])
    p_leaf = _post(client, title="Leafy", status="published", category_id=leaf["id"])

    r = client.delete(f"/cms/categories/{mid['id']}", headers=AUTH["admin"])
    assert r.status_code == 200, r.text
    assert r.json()["moved_children"] == 1 and r.json()["moved_posts"] == 1
    assert r.json()["moved_to_category_id"] == root["id"]

    assert _cat_of(client, leaf["id"])["parent_id"] == root["id"]          # hierarchy preserved
    assert client.get(f"/cms/posts/{p_mid['id']}").json()["category_id"] == root["id"]
    assert client.get(f"/cms/posts/{p_leaf['id']}").json()["category_id"] == leaf["id"]  # untouched
    assert client.get(f"/cms/categories/{mid['id']}").status_code == 404


def test_delete_top_level_category_leaves_children_as_roots_and_posts_uncategorised(client):
    root = _cat(client, "Root")
    child = _cat(client, "Child", root["id"])
    p = _post(client, status="published", category_id=root["id"])
    r = client.delete(f"/cms/categories/{root['id']}", headers=AUTH["admin"])
    assert r.status_code == 200 and r.json()["moved_to_category_id"] is None
    assert _cat_of(client, child["id"])["parent_id"] is None
    assert client.get(f"/cms/posts/{p['id']}").json()["category_id"] is None


def test_delete_category_reassign_to(client):
    root = _cat(client, "Root")
    mid = _cat(client, "Mid", root["id"])
    leaf = _cat(client, "Leaf", mid["id"])
    other = _cat(client, "Other")
    p = _post(client, status="published", category_id=mid["id"])
    h = AUTH["admin"]

    assert client.delete(f"/cms/categories/{mid['id']}?reassign_to={mid['id']}", headers=h).status_code == 400
    assert client.delete(f"/cms/categories/{mid['id']}?reassign_to=999", headers=h).status_code == 400
    # a descendant of the deleted category is not a valid destination (would form a cycle)
    assert client.delete(f"/cms/categories/{mid['id']}?reassign_to={leaf['id']}", headers=h).status_code == 400
    assert client.get(f"/cms/categories/{mid['id']}").status_code == 200  # nothing was deleted by the failures

    r = client.delete(f"/cms/categories/{mid['id']}?reassign_to={other['id']}", headers=h)
    assert r.status_code == 200 and r.json()["moved_to_category_id"] == other["id"]
    assert _cat_of(client, leaf["id"])["parent_id"] == other["id"]
    assert client.get(f"/cms/posts/{p['id']}").json()["category_id"] == other["id"]


def test_delete_category_blocked_by_menu_item_and_permissions(client):
    cat = _cat(client, "News")
    mid = client.post("/cms/menus", json={"name": "Main"}, headers=AUTH["mod"]).json()["id"]
    item = client.post(
        f"/cms/menus/{mid}/items",
        json={"label": "News", "target_type": "category", "target_id": cat["id"]},
        headers=AUTH["mod"],
    ).json()

    assert client.delete(f"/cms/categories/{cat['id']}", headers=AUTH["mod"]).status_code == 403  # admin only
    r = client.delete(f"/cms/categories/{cat['id']}", headers=AUTH["admin"])
    assert r.status_code == 409 and "menu item" in r.json()["detail"]

    client.delete(f"/cms/menus/items/{item['id']}", headers=AUTH["mod"])
    assert client.delete(f"/cms/categories/{cat['id']}", headers=AUTH["admin"]).status_code == 200
    assert client.delete(f"/cms/categories/{cat['id']}", headers=AUTH["admin"]).status_code == 404


# ── delete rules: tags ───────────────────────────────────────────────────
def _tag(client, name):
    r = client.post("/cms/tags", json={"name": name}, headers=AUTH["mod"])
    assert r.status_code == 201, r.text
    return r.json()


def _tag_ids(client, post_id):
    return sorted(t["id"] for t in client.get(f"/cms/posts/{post_id}").json()["tags"])


def test_delete_unused_tag_ok_and_used_tag_needs_force(client):
    h = AUTH["admin"]
    unused, used = _tag(client, "Unused"), _tag(client, "Used")
    p = _post(client, status="published", tag_ids=[used["id"]])

    assert client.delete(f"/cms/tags/{unused['id']}", headers=h).status_code == 200
    r = client.delete(f"/cms/tags/{used['id']}", headers=h)
    assert r.status_code == 409 and "1 post" in r.json()["detail"]
    assert _tag_ids(client, p["id"]) == [used["id"]]                      # still attached

    r = client.delete(f"/cms/tags/{used['id']}?force=true", headers=h)
    assert r.status_code == 200 and r.json()["posts_affected"] == 1
    assert _tag_ids(client, p["id"]) == []                                 # detached...
    assert client.get(f"/cms/posts/{p['id']}").status_code == 200          # ...but the post survives
    assert client.delete(f"/cms/tags/{used['id']}", headers=h).status_code == 404


def test_delete_tag_merge_into(client):
    h = AUTH["admin"]
    old, new, keep = _tag(client, "Old"), _tag(client, "New"), _tag(client, "Keep")
    only_old = _post(client, title="A", status="published", tag_ids=[old["id"]])
    both = _post(client, title="B", status="published", tag_ids=[old["id"], new["id"], keep["id"]])

    assert client.delete(f"/cms/tags/{old['id']}?merge_into={old['id']}", headers=h).status_code == 400
    assert client.delete(f"/cms/tags/{old['id']}?merge_into=999", headers=h).status_code == 400
    assert client.get("/cms/tags").json().__len__() == 3                   # failures changed nothing

    r = client.delete(f"/cms/tags/{old['id']}?merge_into={new['id']}", headers=h)
    assert r.status_code == 200
    assert r.json()["posts_affected"] == 2 and r.json()["posts_moved"] == 1  # `both` already had "New"
    assert _tag_ids(client, only_old["id"]) == [new["id"]]
    assert _tag_ids(client, both["id"]) == sorted([new["id"], keep["id"]])   # no duplicate, others kept


def test_delete_tag_admin_only(client):
    t = _tag(client, "X")
    assert client.delete(f"/cms/tags/{t['id']}", headers=AUTH["mod"]).status_code == 403


# ── frontend gaps: slug lookups, is_featured filter, sort ────────────────
def test_category_and_tag_lookup_by_slug_is_public(client):
    cat = _cat(client, "Hydro Tips")
    tag = _tag(client, "Nutrients")
    r = client.get(f"/cms/categories/slug/{cat['slug']}")          # no auth header
    assert r.status_code == 200 and r.json()["id"] == cat["id"]
    r = client.get(f"/cms/tags/slug/{tag['slug']}")
    assert r.status_code == 200 and r.json()["id"] == tag["id"]
    assert client.get("/cms/categories/slug/nope").status_code == 404
    assert client.get("/cms/tags/slug/nope").status_code == 404
    # the id route still works next to the slug route
    assert client.get(f"/cms/categories/{cat['id']}").status_code == 200


def _titles(client, query="", who=None):
    r = client.get(f"/cms/posts?{query}", headers=AUTH[who] if who else {})
    assert r.status_code == 200, r.text
    return [p["title"] for p in r.json()["results"]]


def test_is_featured_filter(client):
    _post(client, title="Hero", status="published", is_featured=True)
    _post(client, title="Normal", status="published")
    assert _titles(client, "is_featured=true") == ["Hero"]
    assert _titles(client, "is_featured=false") == ["Normal"]
    assert sorted(_titles(client)) == ["Hero", "Normal"]            # omitted -> no filter
    assert client.get("/cms/posts?is_featured=maybe").status_code == 422


def test_sort_by_published_at_and_defaults(client):
    a = _post(client, title="A")                                     # created first
    b = _post(client, title="B")
    c = _post(client, title="C")                                     # stays a draft
    h = AUTH["author"]
    client.post(f"/cms/posts/{b['id']}/publish", headers=h)         # B goes live first...
    client.post(f"/cms/posts/{a['id']}/publish", headers=h)         # ...then A

    # default is unchanged (created_at desc): newest created first
    assert _titles(client) == ["B", "A"]
    assert _titles(client, "", "mod") == ["C", "B", "A"]
    # published_at desc: most recently published first
    assert _titles(client, "sort=published_at") == ["A", "B"]
    assert _titles(client, "sort=published_at&order=asc") == ["B", "A"]
    # unpublished posts (no publish date) sort last in a "newest" list for editors
    assert _titles(client, "sort=published_at&status=draft", "mod") == ["C"]
    assert _titles(client, "sort=published_at", "mod") == ["A", "B", "C"]


def test_sort_by_title_view_count_and_validation(client):
    x = _post(client, title="Banana", status="published")
    _post(client, title="Apple", status="published")
    client.get(f"/cms/posts/slug/{x['slug']}")                       # Banana: 1 view
    assert _titles(client, "sort=title&order=asc") == ["Apple", "Banana"]
    assert _titles(client, "sort=view_count") == ["Banana", "Apple"]
    assert client.get("/cms/posts?sort=password").status_code == 422   # whitelist only
    assert client.get("/cms/posts?order=sideways").status_code == 422


def test_sorting_paginates_stably(client):
    for i in range(5):
        _post(client, title=f"P{i}", status="published")             # equal view_count (0)
    seen = []
    for page in (1, 2, 3):
        seen += _titles(client, f"sort=view_count&page={page}&page_size=2")
    assert sorted(seen) == ["P0", "P1", "P2", "P3", "P4"]            # no dupes, none missing
