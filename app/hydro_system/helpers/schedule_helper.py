# app/hydro_system/helpers/schedule_helper.py

from datetime import datetime, timezone, date
from zoneinfo import ZoneInfo

from app.hydro_system.config import TIMEZONE

LOCAL_TZ = ZoneInfo(TIMEZONE)


def get_local_now() -> datetime:
    """
    Current local datetime.

    Used for schedule comparisons because HydroSchedule.start_time/end_time
    are stored as local TIME values.
    """
    return datetime.now(timezone.utc).astimezone(LOCAL_TZ)

def get_local_today() -> date:
    """
    Current local calendar date (Asia/Ho_Chi_Minh).

    Used for batch growth progression (days_growing) so it does not flip
    at 07:00 local time when the server runs in UTC.
    """
    return get_local_now().date()

def get_utc_now() -> datetime:
    """
    Current UTC datetime.

    Used for:
    - actuator logs
    - interval calculations
    - one-shot timers
    - persisted timestamps
    """
    return datetime.now(timezone.utc)


def get_schedule_context() -> tuple[datetime.time, str]:
    """
    Returns:
        current_time (local)
        current_day  (mon/tue/...)
    """
    now = get_local_now()

    return (
        now.time(),
        now.strftime("%a").lower(),
    )