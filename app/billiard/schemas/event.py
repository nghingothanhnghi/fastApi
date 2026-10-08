# app/billiard/schemas/event.py
from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel, Field

from app.billiard.models.device import DeviceEventType


class DeviceEventIn(BaseModel):
    event_id: str = Field(..., min_length=1, max_length=64)       # idempotency key
    event: DeviceEventType
    # Monotonic per device, survives reboot, starts at 1. Ordering uses THIS,
    # never the timestamp (the ESP32 clock can be wrong while offline).
    device_seq: int = Field(..., ge=1)
    table_id: Optional[int] = None
    timestamp: Optional[datetime] = None
    clock_synced: Optional[bool] = None       # was NTP valid when stamped?
    local_session_id: Optional[str] = Field(None, max_length=64)
    local_game_id: Optional[str] = Field(None, max_length=64)
    data: dict[str, Any] = Field(default_factory=dict)


class EventBatchIn(BaseModel):
    device_id: str
    events: list[DeviceEventIn] = Field(..., max_length=500)


class EventRef(BaseModel):
    event_id: str
    error: str


class EventBatchResult(BaseModel):
    accepted: list[str] = []
    duplicates: list[str] = []
    rejected: list[EventRef] = []
    conflicts: list[EventRef] = []
    # Highest contiguous device_seq the server has applied. The device may
    # discard events up to here and must resend anything above it.
    server_state_version: int = 0