import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session
import sys
import os

# Add project root to sys.path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "../../")))

from main import app
from app.user.utils.token import create_access_token
from app.database import get_db

from app.hydro_system.services.device_service import hydro_device_service

client = TestClient(app)
@pytest.fixture
def test_token():
    return create_access_token(data={"sub": "testuser@example.com"})

@pytest.fixture
def auth_header(test_token):
    return {"Authorization": f"Bearer {test_token}"}

@pytest.fixture(scope="module")
def test_device():
    from app.hydro_system.schemas.device import HydroDeviceCreate

    db: Session = next(get_db())
    external_id = "esp32_dev_001"

    existing = hydro_device_service.get_device_by_external_id(db, external_id)
    if existing:
        return existing

    device_in = HydroDeviceCreate(
        name="Test ESP32",
        device_id=external_id,
        location="Lab A",
        type="ESP32",
        is_active=True,
        client_id="81a41dfa-d1b4-4abc-9302-4bc6d1e93bb2",
        thresholds={},
        user_id=1
    )

    new_device = hydro_device_service.create_device(db, device_in)
    return new_device


def test_send_sensor_data(auth_header, test_device):
    payload = {
        "device_id": test_device.device_id,
        "data": {
            "temperature": 26.5,
            "humidity": 60.2,
            "moisture": 35.1
        }
    }

    response = client.post("/sensor/data", json=payload, headers=auth_header)
    assert response.status_code == 200, f"Failed: {response.status_code} - {response.text}"

    data = response.json()
    assert "id" in data
    assert data["temperature"] == 26.5
    assert data["humidity"] == 60.2
    assert data["moisture"] == 35.1
    assert "created_at" in data
    assert "commands" in data

