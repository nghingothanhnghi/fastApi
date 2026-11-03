# app/tests/test_auth_me_roles.py
# GET /auth/me must expose the caller's active roles so clients can gate UI (CMS editors etc.).
import app.init_db  # noqa: F401  (registers every model)
import pytest
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base, get_db
from app.user.models.role import Role
from app.user.models.user import User
from app.user.models.user_role import UserRole
from app.user.routes.auth_router import router as auth_router
from app.user.utils import token as token_utils


@pytest.fixture()
def env():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine, autoflush=False)
    with Session() as s:
        u = User(client_id="c", username="mod", email="m@x.io", hashed_password="x")
        s.add(u)
        s.add_all([
            Role(name="moderator", display_name="Moderator", is_active=True),
            Role(name="admin", display_name="Admin", is_active=False),   # inactive: must not be reported
        ])
        s.commit()
        for role in s.query(Role).all():
            s.add(UserRole(user_id=u.id, role_id=role.id))
        s.commit()

    app = FastAPI()
    app.include_router(auth_router)

    def _db():
        db = Session()
        try:
            yield db
        finally:
            db.close()

    def _me(db=Depends(get_db)):
        # Same as production: the user is loaded through the request's own session.
        return db.query(User).filter_by(username="mod").one()

    app.dependency_overrides[get_db] = _db
    app.dependency_overrides[token_utils.get_current_user] = _me
    return TestClient(app)


def test_me_includes_active_roles(env):
    r = env.get("/auth/me")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["username"] == "mod"
    assert [role["name"] for role in body["roles"]] == ["moderator"]   # inactive role excluded
    assert "hashed_password" not in body
