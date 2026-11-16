# app/tests/test_sensor_data.py
import os, sys, tempfile
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "../../")))
os.environ.setdefault("DATABASE_URL", f"sqlite:///{tempfile.gettempdir()}/sensor_test_import.db")
os.environ.setdefault("OPENAI_API_KEY", "test")
os.environ.setdefault("SECRET_KEY", "test")

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from main import app
from app.database import Base, get_db
from app.hydro_system.models.device import HydroDevice
from app.hydro_system.models.sensor_data import SensorData


@pytest.fixture()
def client():
    engine = create_engine("sqlite://", poolclass=StaticPool, connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine, autoflush=False)

    def _db():
        db = Session()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = _db
    c = TestClient(app)
    c.Session = Session
    yield c
    app.dependency_overrides.pop(get_db, None)


@pytest.fixture()
def device(client):
    with client.Session() as db:
        d = HydroDevice(name="Test ESP32", device_id="esp32-abc123", external_id="esp32-abc123",
                        type="esp32", user_id=1, client_id="test-client")
        db.add(d)
        db.commit()
        return d.id


def _payload(device_id, **data):
    return {"device_id": device_id, "data": data}


def test_create_sensor_data_success(client, device):
    values = {"temperature": 25.3, "humidity": 50.0, "light": 300.0, "moisture": 45.5, "water_level": 75.0}
    r = client.post("/sensor/data", json=_payload("esp32-abc123", **values))
    assert r.status_code == 200, r.text
    body = r.json()
    for k, v in values.items():
        assert body[k] == v
    with client.Session() as db:
        row = db.query(SensorData).one()
        assert row.device_id == device          # stored against the DB id, not the external id


def test_create_sensor_data_device_not_found(client):
    r = client.post("/sensor/data", json=_payload("unknown-device-999", temperature=22.0))
    assert r.status_code == 404
    assert "not found" in r.json()["detail"].lower()


def test_out_of_range_value_is_422(client, device):
    r = client.post("/sensor/data", json=_payload("esp32-abc123", humidity=150))
    assert r.status_code == 422