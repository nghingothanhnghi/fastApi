# app/billiard/schemas/device.py
from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict

from app.billiard.models.device import DeviceStatus
from app.billiard.models.table import TableStatus


class TableStateOut(BaseModel):
    """What the ESP32 needs to rebuild one table after a reboot."""
    table_id: int
    name: str
    status: TableStatus
    session_id: Optional[int] = None
    session_start_time: Optional[datetime] = None
    session_ends_at: Optional[datetime] = None
    game_id: Optional[int] = None
    game_number: Optional[int] = None
    player_a_score: Optional[int] = None
    player_b_score: Optional[int] = None


class ControllerState(BaseModel):
    device_id: str
    server_time: datetime
    server_state_version: int          # highest contiguous device_seq applied
    tables: list[TableStateOut]


class DeviceStatusOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    device_id: str
    name: str
    status: DeviceStatus
    firmware_version: Optional[str] = None
    last_seen: Optional[datetime] = None
    last_applied_seq: int