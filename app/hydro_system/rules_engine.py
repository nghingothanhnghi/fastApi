# File: app/hydro_system/rules_engine.py
# Description: Rules engine to determine actions based on sensor data
import app.hydro_system.rules
from app.hydro_system.rules.registry import get_rule
from datetime import datetime, time
from app.hydro_system.config import DEFAULT_THRESHOLDS
from app.hydro_system.services.threshold_service import threshold_service
from app.hydro_system.helpers.schedule_helper import (
    get_schedule_context,
    get_utc_now,
)
from app.hydro_system.helpers.comparision_helper import (
    safe_lt,
    safe_gt,
)
from app.core.logging_config import get_logger

logger = get_logger(__name__)


# =========================
# SENSOR RULES
# =========================

def should_refill_water_tank(sensor_data: dict, thresholds: dict) -> bool:
    return safe_lt(sensor_data.get("water_level"), thresholds.get("water_level_min", 20))

def is_water_level_critical(sensor_data: dict, thresholds: dict) -> bool:
    return safe_lt(sensor_data.get("water_level"), thresholds.get("water_level_critical", 10))

def get_water_level_status(sensor_data: dict, thresholds: dict) -> dict:
    """Get detailed water level status and recommendations"""
    water_level = sensor_data.get("water_level", 0)
    
    if water_level is None:
        return {
            "status": "unknown",
            "message": "No water level reading available this cycle.",
            "priority": "low",
            "current_level": None,
            "min_threshold": thresholds.get("water_level_min", 20),
            "critical_threshold": thresholds.get("water_level_critical", 10),
        }

    if water_level < thresholds.get("water_level_critical", 10):
        status, message, priority = "critical", "CRITICAL: Water level extremely low! Immediate refill required.", "high"
    elif water_level < thresholds.get("water_level_min", 20):
        status, message, priority = "low", "Water level low. Refill recommended.", "medium"
    elif water_level > 80:
        status, message, priority = "optimal", "Water level optimal.", "low"
    else:
        status, message, priority = "adequate", "Water level adequate.", "low"

    return {
        "status": status,
        "message": message,
        "priority": priority,
        "current_level": water_level,
        "min_threshold": thresholds.get("water_level_min", 20),
        "critical_threshold": thresholds.get("water_level_critical", 10),
    }

def is_rain_detected(sensor_data: dict) -> bool:
    """Return True if the rain sensor detects rain, otherwise False."""
    return bool(sensor_data.get("rain_detected", False))

def is_flow_blocked(flow_rate: float | None, thresholds: dict) -> bool:
    if flow_rate is None:
        return False
    return flow_rate < thresholds.get("flow_critical", 0.1)


def is_flow_low(flow_rate: float | None, thresholds: dict) -> bool:
    if flow_rate is None:
        return False
    return flow_rate < thresholds.get("flow_min", 0.5)

# =========================
# SCHEDULE / INTERVAL
# =========================

def is_within_schedule_time(schedule, current_time, current_day) -> bool:
    """Helper to check if a specific schedule is active right now"""
    days = [d.strip().lower() for d in schedule.repeat_days.split(",")]

    logger.info(
        f"[SCHEDULE] now={current_time} "
        f"day={current_day} "
        f"start={schedule.start_time} "
        f"end={schedule.end_time} "
        f"repeat={days}"
    )

    if current_day not in days:
        logger.info("[SCHEDULE] Day mismatch")
        return False

    if schedule.start_time <= schedule.end_time:
        result = schedule.start_time <= current_time <= schedule.end_time
    else:
        result = (
            current_time >= schedule.start_time
            or current_time <= schedule.end_time
        )

    logger.info(f"[SCHEDULE] Active={result}")
    return result   
    
def is_in_schedule(actuator) -> tuple[bool, bool]:
    """
    Returns:
    - (is_on_now, has_schedule)
    """
    if not hasattr(actuator, "schedules") or not actuator.schedules:
        return False, False

    # now = datetime.utcnow()
    # current_time = now.time()
    # current_day = now.strftime("%a").lower()
    current_time, current_day = get_schedule_context()

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

    # now = datetime.utcnow()
    # current_time = now.time()
    # current_day = now.strftime("%a").lower()
    utc_now = get_utc_now()
    current_time, current_day = get_schedule_context()

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

    # diff_min = (now - last_log.timestamp).total_seconds() / 60
    diff_min = (
        utc_now - last_log.timestamp
    ).total_seconds() / 60

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

    # now = datetime.utcnow()
    # diff = (now - start).total_seconds()
    utc_now = get_utc_now()

    diff = (
        utc_now - start
    ).total_seconds()

    if diff < duration:
        return True, "running"

    return False, "done"    

def check_rules(
    sensor_data: dict,
    thresholds: dict = DEFAULT_THRESHOLDS,
    actuators: list = [],
    overrides: dict = None,
    recipes: list = [],  # ✅ ADD THIS
    flow_readings: dict = None,   # ✅ NEW — {actuator_id: flow_rate}
) -> dict:
    """
    Evaluate sensor data and decide actions for each actuator, using individual thresholds if available.
    Optionally override global thresholds with `overrides`.
    Supports multiple actuators of the same type.
    Returns a list of per-actuator actions and system alerts.
    """
    actions = []
    alerts = []
    flow_readings = flow_readings or {}

    # Merge overrides if provided
    if overrides:
        thresholds = {**thresholds, **overrides}

    for actuator in actuators:
        actuator_type = actuator.type.lower()
        actuator_id = actuator.id

        # Use thresholds from device, fallback to global
        actuator_thresholds = threshold_service.get_for_device(
            actuator.device
        )

        # ✅ MANUAL override
        manual = getattr(actuator, "manual_state", None)
        actuator_flow = flow_readings.get(actuator_id)  # ✅ per-actuator, not per-device
        logger.info(f"[RULE] actuator={actuator_id} manual={manual}")   


        # =========================
        # SCHEDULE / INTERVAL / ONESHOT
        # =========================
        # Check schedule first
        scheduled_on, has_schedule = is_in_schedule(actuator)

        logger.info(
            "[SCHEDULE RESULT] "
            f"actuator_id={actuator.id} "
            f"type={actuator.type} "
            f"scheduled_on={scheduled_on} "
            f"has_schedule={has_schedule}"
        )

        # recipe
        recipe = next(
            (r for r in recipes if r.actuator_type == actuator_type),
            None
        )

        # ✅ INTERVAL
        interval_on, interval_status = is_in_interval(actuator, recipe)

        logger.info(
            "[INTERVAL RESULT] "
            f"actuator_id={actuator.id} "
            f"type={actuator.type} "
            f"interval_on={interval_on} "
            f"interval_status={interval_status} "
            f"recipe={recipe}"
        )        

        oneshot_on, oneshot_status = is_in_oneshot(actuator)

        # ✅ SENSOR RULE

        rule = get_rule(actuator_type)

        logger.info(
            f"Actuator={actuator_type}, Rule={rule}"
        )

        if rule:
            should_activate = rule.should_activate(
                sensor_data=sensor_data,
                thresholds=actuator_thresholds,
                actuator=actuator,
            )

            logger.info(
                f"[RULE RESULT] {actuator_type} -> {should_activate}"
            )
        else:
            logger.warning(
                f"No rule registered for actuator type '{actuator_type}'"
            )

            should_activate = False

        # =========================
        # PRIORITY SYSTEM
        # =========================
        final_on = False
        reason = "off"

        # 🥇 SAFETY
        if actuator_type == "fan" and safe_gt(sensor_data.get("temperature"), actuator_thresholds.get("temperature_critical", 35)):
            final_on = True
            reason = "safety_high_temp"

        elif actuator_type in ["pump", "water_pump", "nutrient_pump"] and safe_lt(sensor_data.get("water_level"), actuator_thresholds.get("water_level_critical", 10)):
            final_on = False
            reason = "safety_low_water"

        elif sensor_data.get("rain_detected", False):
            rain_actions = actuator_thresholds.get("rain_actuator_actions", {})
            rain_action = rain_actions.get(actuator_type, "ignore")

            if rain_action != "ignore":
                rain_intensity = sensor_data.get("rain_intensity", 0) or 0
                strong_threshold = actuator_thresholds.get("rain_strong_threshold", 10.0)
                is_strong = rain_intensity >= strong_threshold

                final_on = (rain_action == "on")
                reason = f"rain_strong_{rain_action}" if is_strong else f"rain_light_{rain_action}"        

        # ✅ NEW — per-actuator flow safety check
        elif (
            actuator_type in ["pump", "water_pump"]
            and actuator.current_state
            and is_flow_blocked(actuator_flow, actuator_thresholds)
        ):
            final_on = False
            reason = "safety_no_flow"            

        # 🥈 MANUAL (STRONG OVERRIDE)
        elif manual is True:
            final_on = True
            reason = "manual_on"

        elif manual is False:
            final_on = False
            reason = "manual_off"                        

        # 🥉 ONE-SHOT (🔥 NEW)
        elif oneshot_status == "running":
            final_on = True
            reason = "oneshot"

        # 🟡 SCHEDULE (LOCK MODE)
        elif has_schedule:
            final_on = scheduled_on
            # reason = "schedule"
            reason = "schedule" if scheduled_on else "schedule_off"

        # 🔁 INTERVAL (🔥 MAIN CONTROL FOR WATER SYSTEM)
        elif interval_status != "inactive":
            final_on = interval_on
            # reason = "interval"
            reason = "interval" if interval_on else "interval_off"

        # 🌱 SENSOR
        else:
            final_on = should_activate
            # reason = "sensor" if should_activate else "off"
            reason = "sensor" if should_activate else "sensor_off"

        logger.info(
            "[FINAL DECISION] "
            f"actuator_id={actuator_id} "
            f"type={actuator_type} "
            f"sensor={should_activate} "
            f"scheduled_on={scheduled_on} "
            f"has_schedule={has_schedule} "
            f"interval={interval_status} "
            f"manual={manual} "
            f"rain={sensor_data.get('rain_detected')} "
            f"final_on={final_on} "
            f"reason={reason}"
        )

        actions.append({
            "actuator_id": actuator_id,
            "on": final_on,
            "type": actuator_type,
            # 🔍 DEBUG / VISIBILITY
            "reason": reason,
            "manual": manual,

            "scheduled": scheduled_on,
            "has_schedule": has_schedule,

            # 🔁 INTERVAL INFO
            "interval_mode": interval_status,
            "interval_active": interval_status != "inactive",

            # oneshot
            "oneshot": oneshot_status,

            # 🌡 SENSOR INFO
            "sensor_triggered": should_activate,

            "flow_rate": actuator_flow,                               # ✅ NEW
            "flow_blocked": is_flow_blocked(actuator_flow, actuator_thresholds),  # ✅ NEW            

            "rain_detected": sensor_data.get("rain_detected", False),      # ✅ NEW
            "rain_intensity": sensor_data.get("rain_intensity", None), 

            "thresholds_used": actuator_thresholds

        })          

        if is_flow_blocked(actuator_flow, actuator_thresholds):
            alerts.append({
                "type": "critical",
                "message": f"No flow on actuator '{actuator.name or actuator.type}' — possible blockage or dry run",
                "sensor": "flow_rate",
                "actuator_id": actuator_id,
                "value": actuator_flow,
                "action_required": "Check pump, tubing, and water supply immediately",
            })
        elif is_flow_low(actuator_flow, actuator_thresholds):
            alerts.append({
                "type": "warning",
                "message": f"Low flow on actuator '{actuator.name or actuator.type}'",
                "sensor": "flow_rate",
                "actuator_id": actuator_id,
                "value": actuator_flow,
                "action_required": "Inspect for partial blockage or low pressure",
            })        

    # Global/system alerts
    ec = sensor_data.get("ec")
    ppm = sensor_data.get("ppm")

    if safe_gt(ec, thresholds.get("ec_max", 2.5)):
        alerts.append({
            "type": "warning",
            "message": "EC level high",
            "sensor": "ec",
            "value": ec,
            "action_required": "Dilute with fresh water"
        })
    elif ec is not None and 0 < ec < thresholds.get("ec_min", 1.2):
        alerts.append({
            "type": "info",
            "message": "EC level low",
            "sensor": "ec",
            "value": ec,
            "action_required": "Nutrient dosing required"
        })

    if safe_gt(ppm, thresholds.get("ppm_max", 1500)):
        alerts.append({
            "type": "warning",
            "message": "PPM level high",
            "sensor": "ppm",
            "value": ppm,
            "action_required": "Dilute with fresh water"
        })
    elif ppm is not None and 0 < ppm < thresholds.get("ppm_min", 600):
        alerts.append({
            "type": "info",
            "message": "PPM level low",
            "sensor": "ppm",
            "value": ppm,
            "action_required": "Nutrient dosing recommended"
        })

    if sensor_data.get("rain_detected", False):
        rain_intensity = sensor_data.get("rain_intensity", 0) or 0
        strong_threshold = thresholds.get("rain_strong_threshold", 10.0)

        if rain_intensity >= strong_threshold:
            alerts.append({
                "type": "warning",
                "message": f"Strong rain detected ({rain_intensity} mm/hr) — irrigation suppressed",
                "sensor": "rain_intensity",
                "value": rain_intensity,
                "action_required": "None — automatic suppression active; monitor for flooding/runoff"
            })
        else:
            alerts.append({
                "type": "info",
                "message": f"Light rain detected ({rain_intensity} mm/hr) — irrigation suppressed",
                "sensor": "rain_intensity",
                "value": rain_intensity,
                "action_required": "None — automatic suppression active"
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
    if safe_lt(sensor_data.get("moisture"), thresholds.get("moisture_min", 30)) and \
       safe_lt(sensor_data.get("water_level"), thresholds.get("water_level_min", 20)):
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



