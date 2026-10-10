# app/tests/test_sensor_data.py
import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

import sys
import os

# Add project root to sys.path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "../../")))

from main import app
from app.database import get_db
from app.hydro_system.models.device import HydroDevice
from app.hydro_system.models.sensor_data import SensorData
from app.hydro_system.schemas.device import HydroDeviceCreate
from app.database import SessionLocal

client = TestClient(app)

# Use test DB session
def override_get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

app.dependency_overrides[get_db] = override_get_db


@pytest.fixture
def test_device():
    """Create a test device in the DB with a known external_id"""
    db: Session = next(override_get_db())
    device = HydroDevice(
        name="Test ESP32 Device",
        type="esp32",
        external_id="esp32-abc123",
        user_id=1,  # or a test user
        client_id="test-client",
    )
    db.add(device)
    db.commit()
    db.refresh(device)
    yield device

    # Teardown
    db.delete(device)
    db.commit()


def test_create_sensor_data_success(test_device):
    """Simulate ESP32 sending sensor data and ensure it's saved"""
    payload = {
        "device_id": "esp32-abc123",  # external_id
        "temperature": 25.3,
        "humidity": 50.0,
        "light": 300.0,
        "moisture": 45.5,
        "water_level": 75.0,
    }

    response = client.post("/sensor/data", json=payload)
    assert response.status_code == 200

    data = response.json()
    assert data["temperature"] == payload["temperature"]
    assert data["humidity"] == payload["humidity"]
    assert data["device_id"] == test_device.id


def test_create_sensor_data_device_not_found():
    """If ESP32 sends unknown external_id, it should return 404"""
    payload = {
        "device_id": "unknown-device-999",
        "temperature": 22.0,
        "humidity": 60.0,
        "light": 150.0,
        "moisture": 40.0,
        "water_level": 60.0,
    }

    response = client.post("/sensor/data", json=payload)
    assert response.status_code == 404
    assert "not found" in response.json()["detail"].lower()
