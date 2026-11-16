# app/tests/test_hydro_system.py
import os, tempfile
os.environ.setdefault("DATABASE_URL", f"sqlite:///{tempfile.gettempdir()}/hydro_test_import.db")
os.environ.setdefault("OPENAI_API_KEY", "test")
os.environ.setdefault("SECRET_KEY", "test")

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import app.init_db  # noqa: F401  registers every model
from app.database import Base
from app.hydro_system.controllers import system_controller
from app.hydro_system.models.actuator import HydroActuator
from app.hydro_system.models.actuator_log import HydroActuatorLog
from app.hydro_system.models.device import HydroDevice
from app.hydro_system.schemas.device import HydroDeviceCreate
from app.hydro_system.services.device_service import HydroDeviceService


@pytest.fixture()
def db():
    engine = create_engine("sqlite://", poolclass=StaticPool, connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    s = sessionmaker(bind=engine, autoflush=False)()
    yield s
    s.close()


def _device_with_pump(db, user_id=7):
    dev = HydroDevice(name="D", device_id="x", user_id=user_id)
    db.add(dev)
    db.flush()
    pump = HydroActuator(type="pump", name="P", pin="25", port=1, device_id=dev.id)
    db.add(pump)
    db.commit()
    return dev, pump


def test_device_service_create_and_get(db):
    svc = HydroDeviceService()
    dev = svc.create_device(db, HydroDeviceCreate(name="Device1", device_id="esp1", user_id=42))
    assert dev.id is not None
    assert svc.get_device(db, dev.id).device_id == "esp1"


def test_duplicate_device_id_is_rejected(db):
    svc = HydroDeviceService()
    svc.create_device(db, HydroDeviceCreate(name="A", device_id="esp1", user_id=1))
    with pytest.raises(HTTPException) as e:
        svc.create_device(db, HydroDeviceCreate(name="B", device_id="esp1", user_id=1))
    assert e.value.status_code == 400


def test_get_system_status_user(db, monkeypatch):
    # read_sensors opens its own SessionLocal (the real DB), so stub it.
    monkeypatch.setattr(system_controller.sensors, "read_sensors",
                        lambda device_id=None, **kw: {"temperature": 25.0})
    dev, pump = _device_with_pump(db)

    status = system_controller.get_system_status(db, user_id=7)

    assert isinstance(status, list) and len(status) == 1
    item = status[0]
    assert item["device_id"] == dev.id
    assert item["sensors"]["temperature"] == 25.0
    assert item["sensors"]["rain_detected_effective"] is False
    assert [a["id"] for a in item["actuators"]] == [pump.id]
    assert all(a["current_state"] is False for a in item["actuators"])
    assert item["growing_batch"] is None


def test_get_system_status_unknown_user_is_404(db, monkeypatch):
    monkeypatch.setattr(system_controller.sensors, "read_sensors", lambda **kw: {})
    with pytest.raises(HTTPException) as e:
        system_controller.get_system_status(db, user_id=999)
    assert e.value.status_code == 404


def test_control_actuator_by_id_persists_state_and_logs(db):
    _, pump = _device_with_pump(db)

    result = system_controller.control_actuator_by_id(db, pump.id, True)

    db.refresh(pump)
    assert result["new_state"] is True and pump.current_state is True
    assert pump.last_state_changed_at is not None
    log = db.query(HydroActuatorLog).one()
    assert (log.actuator_id, log.action, log.state, log.source) == (pump.id, "on", "ON", "user")


def test_control_unknown_actuator_is_404(db):
    with pytest.raises(HTTPException) as e:
        system_controller.control_actuator_by_id(db, 9999, True)
    assert e.value.status_code == 404


def test_manual_mode_applies_immediately_and_auto_clears_it(db):
    _, pump = _device_with_pump(db)

    r = system_controller.set_manual_mode(db, pump.id, True)
    db.refresh(pump)
    assert r["mode"] == "manual_on" and pump.manual_state is True and pump.current_state is True

    r = system_controller.set_manual_mode(db, pump.id, None)
    db.refresh(pump)
    assert r["mode"] == "auto" and pump.manual_state is None