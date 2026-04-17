# File: app/hydro_system/rules_engine.py
# Description: Rules engine to determine actions based on sensor data

from datetime import datetime, time
from app.hydro_system.config import DEFAULT_THRESHOLDS
from app.hydro_system.models import sensor_data
from app.hydro_system.models.actuator import HydroActuator
from app.core.logging_config import get_logger

logger = get_logger(__name__)


# =========================
# SENSOR RULES
# =========================

def should_turn_on_pump(sensor_data: dict, thresholds: dict) -> bool:
    """Check if irrigation pump should be turned on based on soil moisture"""
    moisture = sensor_data.get("moisture", 0)
    water_level = sensor_data.get("water_level", 0)
    
    # Don't turn on pump if water level is too low
    if water_level < thresholds.get("water_level_min", 20):
        logger.warning(f"Cannot turn on pump: Water level too low ({water_level}%)")
        return False
    
    return moisture < thresholds.get("moisture_min", 30)

def should_turn_on_light(sensor_data: dict, thresholds: dict) -> bool:
    """Check if grow lights should be turned on based on light intensity"""
    light = sensor_data.get("light", 0)
    return light < thresholds.get("light_min", 300)

def should_turn_on_fan(sensor_data: dict, thresholds: dict) -> bool:
    """Check if ventilation fan should be turned on based on temperature"""
    temperature = sensor_data.get("temperature", 0)
    return temperature > thresholds.get("temperature_max", 28)

def should_refill_water_tank(sensor_data: dict, thresholds: dict) -> bool:
    """Check if water tank needs refilling"""
    water_level = sensor_data.get("water_level", 0)
    return water_level < thresholds.get("water_level_min", 20)

def is_water_level_critical(sensor_data: dict, thresholds: dict) -> bool:
    """Check if water level is critically low (emergency alert)"""
    water_level = sensor_data.get("water_level", 0)
    return water_level < thresholds.get("water_level_critical", 10)

def get_water_level_status(sensor_data: dict, thresholds: dict) -> dict:
    """Get detailed water level status and recommendations"""
    water_level = sensor_data.get("water_level", 0)
    
    if water_level < thresholds.get("water_level_critical", 10):
        status = "critical"
        message = "CRITICAL: Water level extremely low! Immediate refill required."
        priority = "high"
    elif water_level < thresholds.get("water_level_min", 20):
        status = "low"
        message = "Water level low. Refill recommended."
        priority = "medium"
    elif water_level > 80:
        status = "optimal"
        message = "Water level optimal."
        priority = "low"
    else:
        status = "adequate"
        message = "Water level adequate."
        priority = "low"
    
    return {
        "status": status,
        "message": message,
        "priority": priority,
        "current_level": water_level,
        "min_threshold": thresholds.get("water_level_min", 20),
        "critical_threshold": thresholds.get("water_level_critical", 10)
    }

def should_turn_on_water_pump(sensor_data: dict, thresholds: dict) -> bool:
    """
    Determine if the water pump should be turned on.
    Example logic: used to refill internal reservoirs when main tank is sufficient
    """
    water_level = sensor_data.get("water_level", 0)
    return water_level > thresholds.get("water_level_min", 20)  # Example: pump if water is available

def should_open_valve(sensor_data: dict, thresholds: dict) -> bool:
    """
    Determine if a valve should be opened.
    Example logic: open valve if soil is dry and water level is sufficient
    """
    moisture = sensor_data.get("moisture", 0)
    water_level = sensor_data.get("water_level", 0)

    if water_level < thresholds.get("water_level_min", 20):
        logger.warning("Cannot open valve: Water level too low")
        return False

    return moisture < thresholds.get("moisture_min", 30)

def should_dose_nutrients(sensor_data: dict, thresholds: dict) -> bool:
    """
    Determine if the nutrient pump should be turned on.
    Logic: dose if EC or PPM is below the minimum threshold.
    """
    ec = sensor_data.get("ec", 0)
    ppm = sensor_data.get("ppm", 0)
    
    # Priority on EC, fallback to PPM if EC is 0 (missing)
    if ec > 0:
        return ec < thresholds.get("ec_min", 1.2)
    
    if ppm > 0:
        return ppm < thresholds.get("ppm_min", 600)
    
    return False


# =========================
# SCHEDULE / INTERVAL
# =========================

def is_within_schedule_time(schedule, current_time, current_day) -> bool:
    """Helper to check if a specific schedule is active right now"""
    days = [d.strip().lower() for d in schedule.repeat_days.split(",")]
    if current_day not in days:
        return False

    if schedule.start_time <= schedule.end_time:
        return schedule.start_time <= current_time <= schedule.end_time
    else:
        return current_time >= schedule.start_time or current_time <= schedule.end_time    
    
def is_in_schedule(actuator) -> tuple[bool, bool]:
    """
    Returns:
    - (is_on_now, has_schedule)
    """
    if not hasattr(actuator, "schedules") or not actuator.schedules:
        return False, False

    now = datetime.utcnow()
    current_time = now.time()
    current_day = now.strftime("%a").lower()

    has_schedule = False

    for schedule in actuator.schedules:
        if not schedule.is_active:
            continue

        # skip interval schedules
        if schedule.interval_on_min or schedule.interval_off_min:
            continue

        has_schedule = True

        if is_within_schedule_time(schedule, current_time, current_day):
            return True, True

    return False, has_schedule    

def is_in_interval(actuator, recipe=None) -> tuple[bool, str]:
    now = datetime.utcnow()
    current_time = now.time()
    current_day = now.strftime("%a").lower()

    active_interval = None

    # 1. actuator schedule first
    if hasattr(actuator, "schedules"):
        for schedule in actuator.schedules:
            if not schedule.is_active:
                continue

            if schedule.interval_on_min and schedule.interval_off_min:
                if is_within_schedule_time(schedule, current_time, current_day):
                    active_interval = schedule
                    break

    # 2. fallback recipe
    if not active_interval and recipe and recipe.action == "interval":
        start = recipe.start_time or time(0, 0)
        end = recipe.end_time or time(23, 59)

        in_window = (
            start <= current_time <= end
            if start <= end
            else current_time >= start or current_time <= end
        )

        if in_window:
            active_interval = recipe

    if not active_interval:
        return False, "inactive"

    on_min = active_interval.interval_on_min
    off_min = active_interval.interval_off_min

    # last log
    last_log = None
    if hasattr(actuator, "logs") and actuator.logs:
        last_log = sorted(actuator.logs, key=lambda x: x.timestamp, reverse=True)[0]

    if not last_log:
        return True, "active_on"

    diff_min = (now - last_log.timestamp).total_seconds() / 60
    last_state = (last_log.state or "OFF").upper()

    if last_state == "ON":
        return (diff_min < on_min), "active_on" if diff_min < on_min else "active_off"
    else:
        return (diff_min >= off_min), "active_on" if diff_min >= off_min else "active_off"
    
def is_in_oneshot(actuator) -> tuple[bool, str]:
    """
    Check if actuator is running a one-shot action (run for X seconds)
    """
    if not hasattr(actuator, "oneshot") or not actuator.oneshot:
        return False, "inactive"

    start = actuator.oneshot.get("start_time")
    duration = actuator.oneshot.get("duration_sec")

    if not start or not duration:
        return False, "inactive"

    now = datetime.utcnow()
    diff = (now - start).total_seconds()

    if diff < duration:
        return True, "running"

    return False, "done"    

def check_rules(
    sensor_data: dict,
    thresholds: dict = DEFAULT_THRESHOLDS,
    actuators: list = [],
    overrides: dict = None,
    recipes: list = []  # ✅ ADD THIS
) -> dict:
    """
    Evaluate sensor data and decide actions for each actuator, using individual thresholds if available.
    Optionally override global thresholds with `overrides`.
    Supports multiple actuators of the same type.
    Returns a list of per-actuator actions and system alerts.
    """
    actions = []
    alerts = []

    # Merge overrides if provided
    if overrides:
        thresholds = {**thresholds, **overrides}

    for actuator in actuators:
        actuator_type = actuator.type.lower()
        actuator_id = actuator.id

        # Use thresholds from device, fallback to global
        actuator_thresholds = getattr(actuator.device, "thresholds", {}) or thresholds


        # ✅ MANUAL override
        manual = None
        if overrides and "actuators" in overrides:
            manual = overrides["actuators"].get(str(actuator_id))        

        # Check schedule first
        scheduled_on, has_schedule = is_in_schedule(actuator)

        # recipe
        recipe = next(
            (r for r in recipes if r.actuator_type == actuator_type),
            None
        )

        # ✅ INTERVAL
        interval_on, interval_status = is_in_interval(actuator, recipe)

        oneshot_on, oneshot_status = is_in_oneshot(actuator)

        # ✅ SENSOR RULE
        should_activate = False

        if actuator_type == "pump":
            should_activate = should_turn_on_pump(sensor_data, actuator_thresholds)
        elif actuator_type == "light":
            should_activate = should_turn_on_light(sensor_data, actuator_thresholds)
        elif actuator_type == "fan":
            should_activate = should_turn_on_fan(sensor_data, actuator_thresholds)
        elif actuator_type == "valve":
            should_activate = should_open_valve(sensor_data, actuator_thresholds)
        elif actuator_type == "water_pump":
            should_activate = should_turn_on_water_pump(sensor_data, actuator_thresholds)
        elif actuator_type == "nutrient_pump":
            should_activate = should_dose_nutrients(sensor_data, actuator_thresholds)

        # ✅ 2. EVALUATE PRIORITIES
        final_on = False
        reason = "off"

        # 🥇 SAFETY
        if actuator_type == "fan" and sensor_data.get("temperature", 0) > actuator_thresholds.get("temperature_critical", 35):
            final_on = True
            reason = "safety_high_temp"

        elif actuator_type in ["pump", "water_pump", "nutrient_pump"] and sensor_data.get("water_level", 0) < actuator_thresholds.get("water_level_critical", 10):
            final_on = False
            reason = "safety_low_water"

        # 🥈 MANUAL (hard override)
        elif manual is not None:
            final_on = manual
            reason = "manual"

        # 🥉 ONE-SHOT (🔥 NEW)
        elif oneshot_status == "running":
            final_on = True
            reason = "oneshot"

        # 🟡 SCHEDULE (LOCK MODE)
        elif has_schedule:
            final_on = scheduled_on
            reason = "schedule"

        # 🔁 INTERVAL
        elif interval_status != "inactive":
            final_on = interval_on
            reason = "interval"

        # 🌱 SENSOR
        else:
            final_on = should_activate
            reason = "sensor" if should_activate else "off"

        actions.append({
            "actuator_id": actuator_id,
            "on": final_on,
            "type": actuator_type,
            # 🔍 DEBUG / VISIBILITY
            "thresholds_used": actuator_thresholds,
            "reason": reason,

            "scheduled": scheduled_on,
            "has_schedule": has_schedule,

            # 🔁 INTERVAL INFO
            "interval_mode": interval_status,
            "interval_active": interval_status != "inactive",

            # oneshot
            "oneshot": oneshot_status,

            # 🌡 SENSOR INFO
            "sensor_triggered": should_activate,
            # 🧑 MANUAL
            "manual": manual
        })

    # Global/system alerts
    ec = sensor_data.get("ec", 0)
    ppm = sensor_data.get("ppm", 0)

    if ec > thresholds.get("ec_max", 2.5):
        alerts.append({
            "type": "warning",
            "message": "EC level high",
            "sensor": "ec",
            "value": ec,
            "action_required": "Dilute with fresh water"
        })
    elif ec > 0 and ec < thresholds.get("ec_min", 1.2):
        alerts.append({
            "type": "info",
            "message": "EC level low",
            "sensor": "ec",
            "value": ec,
            "action_required": "Nutrient dosing required"
        })

    if ppm > thresholds.get("ppm_max", 1500):
        alerts.append({
            "type": "warning",
            "message": "PPM level high",
            "sensor": "ppm",
            "value": ppm,
            "action_required": "Dilute with fresh water"
        })
    elif ppm > 0 and ppm < thresholds.get("ppm_min", 600):
        alerts.append({
            "type": "info",
            "message": "PPM level low",
            "sensor": "ppm",
            "value": ppm,
            "action_required": "Nutrient dosing recommended"
        })

    if is_water_level_critical(sensor_data, thresholds):
        alerts.append({
            "type": "critical",
            "message": "Water level critically low!",
            "sensor": "water_level",
            "value": sensor_data.get("water_level", 0),
            "action_required": "Immediate water tank refill"
        })
    elif should_refill_water_tank(sensor_data, thresholds):
        alerts.append({
            "type": "warning",
            "message": "Water level low",
            "sensor": "water_level",
            "value": sensor_data.get("water_level", 0),
            "action_required": "Schedule water tank refill"
        })

    # Compound alert
    if sensor_data.get("moisture", 0) < thresholds.get("moisture_min", 30) and \
       sensor_data.get("water_level", 0) < thresholds.get("water_level_min", 20):
        alerts.append({
            "type": "warning",
            "message": "Cannot irrigate: Both soil moisture and water level are low",
            "sensor": "moisture_water_level",
            "action_required": "Refill water tank before irrigation"
        })

    return {
        "actions": actions,
        "alerts": alerts,
        "water_status": get_water_level_status(sensor_data, thresholds)
    }



