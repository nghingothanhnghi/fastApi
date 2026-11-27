# app/billiard/config.py
import os
from decimal import Decimal
from enum import Enum
from zoneinfo import ZoneInfo


class BillingPolicy(str, Enum):
    PER_MINUTE = "per_minute"      # 90 min = 1.5 x hourly_rate
    ROUNDED_HOUR = "rounded_hour"  # 1-60 min = 1h, 61-120 = 2h, ...


# Default policy for NEW sessions. Each session snapshots the policy and the
# hourly rate at start, so changing config/rates never alters a running or old bill.
BILLING_POLICY = BillingPolicy(os.getenv("BILLIARD_BILLING_POLICY", "per_minute"))
MIN_BILLABLE_MINUTES = int(os.getenv("BILLIARD_MIN_BILLABLE_MINUTES", "1"))
# Round the final table fee to a currency unit (e.g. 1000 for VND). 1 = no rounding.
FEE_ROUNDING_UNIT = Decimal(os.getenv("BILLIARD_FEE_ROUNDING_UNIT", "1"))
CURRENCY = os.getenv("BILLIARD_CURRENCY", "VND")

MAX_CLOCK_AHEAD_SECONDS = int(os.getenv("BILLIARD_MAX_CLOCK_AHEAD_SECONDS", "120"))
MAX_OFFLINE_HOURS = int(os.getenv("BILLIARD_MAX_OFFLINE_HOURS", "48"))

# Timezone the club operates in. Report date ranges are interpreted in this
# timezone, then converted to UTC for querying (end_time is stored in UTC).
TIMEZONE = os.getenv("BILLIARD_TIMEZONE", "Asia/Ho_Chi_Minh")
LOCAL_TZ = ZoneInfo(TIMEZONE)

# Controller watchdog: a device silent for MORE than this is stored and shown as offline.
OFFLINE_AFTER_SECONDS = int(os.getenv("BILLIARD_OFFLINE_AFTER_SECONDS", "90"))
# How often the watchdog job looks for silent controllers.
WATCHDOG_INTERVAL_SECONDS = int(os.getenv("BILLIARD_WATCHDOG_INTERVAL_SECONDS", "30"))

# POS WebSocket (WS /ws/billiard): the server sends {"type": "ping"} this often, so a half-open
# connection is noticed and proxies do not close an idle one.
WS_PING_SECONDS = float(os.getenv("BILLIARD_WS_PING_SECONDS", "30"))
# A client that cannot take a message within this time is treated as dead and dropped.
WS_SEND_TIMEOUT_SECONDS = float(os.getenv("BILLIARD_WS_SEND_TIMEOUT_SECONDS", "5"))
