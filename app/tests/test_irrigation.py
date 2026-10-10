# tests/test_irrigation.py
#
# Uses an in-memory SQLite DB, mirroring how this project's other tests would
# be set up against app.database.Base. Run with: pytest tests/test_irrigation.py

import pytest
from datetime import datetime, timedelta, timezone

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database import Base
from app.hydro_system.models.device import HydroDevice
from app.hydro_system.models.actuator import HydroActuator
from app.hydro_system.models.flow_reading import HydroFlowReading
from app.hydro_system.models.irrigation import (
    IrrigationSession, IrrigationSessionStatus, ZoneBaselineSettings, WaterEfficiencyAlert,
)
from app.hydro_system.schemas.irrigation import IrrigationSessionStart, ZoneBaselineUpdate
from app.hydro_system.services.irrigation_session_service import irrigation_session_service
from app.hydro_system.services.baseline_service import baseline_service
from app.hydro_system.services.water_efficiency_service import water_efficiency_service


@pytest.fixture()
def db():
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    SessionLocal = sessionmaker(bind=engine)
    session = SessionLocal()
    yield session
    session.close()


@pytest.fixture()
def device(db):
    d = HydroDevice(name="Zone A", device_id="esp32-test-001", user_id=1, is_active=True)
    db.add(d)
    db.commit()
    db.refresh(d)
    return d


@pytest.fixture()
def actuator(db, device):
    a = HydroActuator(type="pump", name="Pump 1", port=1, device_id=device.id, is_active=True)
    db.add(a)
    db.commit()
    db.refresh(a)
    return a


def _add_reading(db, actuator_id, device_id, flow_rate, at):
    r = HydroFlowReading(actuator_id=actuator_id, device_id=device_id, flow_rate=flow_rate, created_at=at)
    db.add(r)
    db.commit()
    return r


# ── Flow / session volume calculation ────────────────────────────────────

def test_session_volume_calculation_trapezoidal(db, device, actuator):
    """2 readings, 10 min apart, flow rises from 4 -> 6 L/min ⇒ 50L (trapezoid)."""
    start = IrrigationSessionStart(actuator_id=actuator.id, device_id=device.id)
    session = irrigation_session_service.start_session(db, start)

    t0 = session.start_time
    _add_reading(db, actuator.id, device.id, 4.0, t0)
    _add_reading(db, actuator.id, device.id, 6.0, t0 + timedelta(minutes=10))

    stopped = irrigation_session_service.stop_session(db, session.id)

    assert stopped.status == IrrigationSessionStatus.completed
    assert stopped.actual_volume_liters == pytest.approx(50.0, rel=1e-3)
    assert stopped.average_flow_lpm == pytest.approx(5.0, rel=1e-3)
    assert stopped.max_flow_lpm == pytest.approx(6.0, rel=1e-3)


def test_session_volume_single_reading_uses_duration_fallback(db, device, actuator):
    start = IrrigationSessionStart(actuator_id=actuator.id, device_id=device.id)
    session = irrigation_session_service.start_session(db, start)
    _add_reading(db, actuator.id, device.id, 3.0, session.start_time)

    stopped = irrigation_session_service.stop_session(db, session.id)
    assert stopped.average_flow_lpm == pytest.approx(3.0)
    # actual_volume ~= average_flow * elapsed_minutes (elapsed ~ 0 in test, so >= 0)
    assert stopped.actual_volume_liters >= 0.0


# ── Idempotency / duplicate prevention ───────────────────────────────────

def test_start_session_idempotent_per_actuator(db, device, actuator):
    start = IrrigationSessionStart(actuator_id=actuator.id, device_id=device.id)
    first = irrigation_session_service.start_session(db, start)
    second = irrigation_session_service.start_session(db, start)

    assert first.id == second.id
    count = db.query(IrrigationSession).filter(IrrigationSession.actuator_id == actuator.id).count()
    assert count == 1


def test_stop_session_idempotent(db, device, actuator):
    start = IrrigationSessionStart(actuator_id=actuator.id, device_id=device.id)
    session = irrigation_session_service.start_session(db, start)
    _add_reading(db, actuator.id, device.id, 5.0, session.start_time)

    first_stop = irrigation_session_service.stop_session(db, session.id)
    second_stop = irrigation_session_service.stop_session(db, session.id)

    assert first_stop.actual_volume_liters == second_stop.actual_volume_liters
    assert first_stop.end_time == second_stop.end_time


# ── Baseline / liters-per-m2 / saving % ──────────────────────────────────

def test_liters_per_m2_and_baseline_comparison(db, device, actuator):
    baseline_service.update(
        db, device.id,
        ZoneBaselineUpdate(area_m2=10.0, baseline_weekly_liters=100.0, efficiency_threshold_percent=20.0),
    )

    # One completed session using 80L this week -> under baseline
    session = IrrigationSession(
        actuator_id=actuator.id, device_id=device.id, zone_id=device.id,
        start_time=datetime.now(timezone.utc) - timedelta(days=1),
        end_time=datetime.now(timezone.utc),
        status=IrrigationSessionStatus.completed,
        actual_volume_liters=80.0, average_flow_lpm=4.0, max_flow_lpm=6.0,
        duration_seconds=1200,
    )
    db.add(session)
    db.commit()

    result = water_efficiency_service.get_efficiency(db, zone_id=device.id, range_key="7d")

    assert result["water_usage"]["current_liters"] == pytest.approx(80.0)
    assert result["water_usage"]["baseline_liters"] == pytest.approx(100.0)
    assert result["water_usage"]["saving_liters"] == pytest.approx(20.0)
    assert result["water_usage"]["saving_percent"] == pytest.approx(20.0)
    assert result["efficiency"]["liters_per_m2"] == pytest.approx(8.0)
    assert result["efficiency"]["status"] == "efficient"


def test_excessive_consumption_triggers_status_and_alert(db, device, actuator):
    baseline_service.update(
        db, device.id,
        ZoneBaselineUpdate(area_m2=10.0, baseline_weekly_liters=100.0, efficiency_threshold_percent=20.0),
    )

    session = IrrigationSession(
        actuator_id=actuator.id, device_id=device.id, zone_id=device.id,
        start_time=datetime.now(timezone.utc) - timedelta(days=1),
        end_time=datetime.now(timezone.utc),
        status=IrrigationSessionStatus.completed,
        actual_volume_liters=150.0,  # 50% over baseline -> excessive (threshold 20%)
        average_flow_lpm=5.0, max_flow_lpm=7.0, duration_seconds=1800,
    )
    db.add(session)
    db.commit()

    result = water_efficiency_service.get_efficiency(db, zone_id=device.id, range_key="7d")

    assert result["efficiency"]["status"] == "excessive"
    alerts = db.query(WaterEfficiencyAlert).filter(WaterEfficiencyAlert.zone_id == device.id).all()
    assert len(alerts) == 1
    assert alerts[0].difference_percent == pytest.approx(50.0)


def test_duplicate_efficiency_alerts_are_not_created(db, device, actuator):
    baseline_service.update(
        db, device.id,
        ZoneBaselineUpdate(baseline_weekly_liters=100.0, efficiency_threshold_percent=10.0),
    )
    db.add(IrrigationSession(
        actuator_id=actuator.id, device_id=device.id, zone_id=device.id,
        start_time=datetime.now(timezone.utc) - timedelta(hours=2),
        end_time=datetime.now(timezone.utc),
        status=IrrigationSessionStatus.completed,
        actual_volume_liters=200.0, average_flow_lpm=5.0, max_flow_lpm=5.0, duration_seconds=600,
    ))
    db.commit()

    # Call twice with the exact same range/date-window -> same period_start -> deduped
    water_efficiency_service.get_efficiency(db, zone_id=device.id, range_key="7d")
    water_efficiency_service.get_efficiency(db, zone_id=device.id, range_key="7d")

    alerts = db.query(WaterEfficiencyAlert).filter(WaterEfficiencyAlert.zone_id == device.id).all()
    assert len(alerts) == 1


# ── Date-range statistics ────────────────────────────────────────────────

def test_statistics_respects_date_range_filtering(db, device, actuator):
    now = datetime.now(timezone.utc)

    in_range = IrrigationSession(
        actuator_id=actuator.id, device_id=device.id, zone_id=device.id,
        start_time=now - timedelta(hours=1), end_time=now,
        status=IrrigationSessionStatus.completed,
        actual_volume_liters=30.0, average_flow_lpm=3.0, max_flow_lpm=4.0, duration_seconds=600,
    )
    out_of_range = IrrigationSession(
        actuator_id=actuator.id, device_id=device.id, zone_id=device.id,
        start_time=now - timedelta(days=10), end_time=now - timedelta(days=10),
        status=IrrigationSessionStatus.completed,
        actual_volume_liters=999.0, average_flow_lpm=9.0, max_flow_lpm=9.0, duration_seconds=600,
    )
    db.add_all([in_range, out_of_range])
    db.commit()

    stats = water_efficiency_service.get_statistics(db, zone_id=device.id, range_key="7d")

    assert stats["sessions"] == 1
    assert stats["total_liters"] == pytest.approx(30.0)


def test_only_completed_sessions_count_toward_statistics(db, device, actuator):
    now = datetime.now(timezone.utc)
    db.add(IrrigationSession(
        actuator_id=actuator.id, device_id=device.id, zone_id=device.id,
        start_time=now, status=IrrigationSessionStatus.running,
        actual_volume_liters=0.0,
    ))
    db.commit()

    stats = water_efficiency_service.get_statistics(db, zone_id=device.id, range_key="today")
    assert stats["sessions"] == 0
    assert stats["total_liters"] == 0.0
