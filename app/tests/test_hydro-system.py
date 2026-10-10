

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from types import SimpleNamespace
from unittest.mock import MagicMock
import sys
import os

# Add project root to sys.path so 'app' module resolves correctly
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "../../")))
from main import app
from app.hydro_system.controllers.system_controller import (
    get_system_status,
    control_actuator_by_id as system_control_actuator
)
from app.hydro_system.controllers.actuator_controller import (
    control_actuator as actuator_control
)
from app.hydro_system.services.device_service import HydroDeviceService
from app.hydro_system.models.device import HydroDevice
from app.hydro_system.schemas.device import HydroDeviceCreate
from app.hydro_system.models.actuator import HydroActuator
from app.database import Base

# Setup in-memory SQLite for testing
en_v = "sqlite:///:memory:"
engine = create_engine(en_v, connect_args={"check_same_thread": False})
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

@pytest.fixture(scope="module")
def db_session():
    Base.metadata.create_all(bind=engine)
    session = TestingSessionLocal()
    yield session
    session.close()

@pytest.fixture(autouse=True)
def override_get_db(monkeypatch, db_session):
    def _get_db():
        try:
            yield db_session
        finally:
            pass
    monkeypatch.setattr("app.database.get_db", _get_db)

# Mock external dependencies
@pytest.fixture(autouse=True)
def mock_deps(monkeypatch):
    monkeypatch.setattr(
        "app.hydro_system.controllers.hydro_system_controller.sensors.read_sensors",
        lambda device_id: {"temp": 1}
    )
    monkeypatch.setattr(
        "app.hydro_system.controllers.hydro_system_controller.state_manager.get_state",
        lambda key: False
    )
    monkeypatch.setattr(
        "app.hydro_system.controllers.hydro_system_controller.check_rules",
        lambda data, thresholds: {"actions": {}, "alerts": []}
    )

# 1. Test DeviceService

def test_device_service_create_and_get(db_session):
    svc = HydroDeviceService()
    create_in = HydroDeviceCreate(name='Device1', device_id='esp1', user_id=42)
    dev = svc.create_device(db_session, create_in)
    assert dev.id is not None
    fetched = svc.get_device(db_session, dev.id)
    assert fetched.device_id == 'esp1'

# 2. Test get_system_status (by user)
def test_get_system_status_user(db_session):
    dev = HydroDevice(name='D', device_id='x', user_id=7)
    db_session.add(dev)
    db_session.commit()
    status = get_system_status(db_session, user_id=7)
    assert status['device_id'] == dev.id
    assert status['sensors'] == {'temp': 1}
    assert all(val is False for val in status['actuators'].values())

# 3. Test actuator_controller.control_actuator

def test_actuator_control_logs_and_state(monkeypatch, db_session):
    # Spy on state_manager.set_state and log_actuator_action
    set_calls = {}
    monkeypatch.setattr(
        'app.hydro_system.controllers.actuator_controller.set_state',
        lambda key, val: set_calls.setdefault('state', (key, val))
    )
    log_calls = {}
    monkeypatch.setattr(
        'app.hydro_system.controllers.actuator_controller.log_actuator_action',
        lambda db, aid, state: log_calls.setdefault('log', (aid, state))
    )
    # Call without pre-existing actuator => fallback
    actuator_control(db_session, 'pump', True, device_id=None)
    assert set_calls['state'][1] is True
    assert log_calls['log'][1] is True

# 4. Test system_controller.control_actuator invokes actuator_controller

def test_system_control_integration(monkeypatch, db_session):
    called = {}
    monkeypatch.setattr(
        'app.hydro_system.controllers.hydro_system_controller.actuator_controller.control_actuator',
        lambda db, typ, on, did: called.update({'type': typ, 'on': on})
    )
    system_control_actuator(db_session, 'fan', True, user_id=5, device_id=99)
    assert called['type'] == 'fan'
    assert called['on'] is True
