# app/billiard/models/device.py
# Central ESP32 controller, its event inbox, and offline local-id mapping.
import enum
from datetime import datetime

from sqlalchemy import (
    BigInteger, Boolean, CheckConstraint, DateTime, ForeignKey, Index, Integer, JSON,
    String, Text, UniqueConstraint, func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base
from ._common import enum_col


class DeviceStatus(str, enum.Enum):
    ONLINE = "online"
    OFFLINE = "offline"
    SYNCING = "syncing"
    ERROR = "error"


class DeviceEventType(str, enum.Enum):
    HEARTBEAT = "heartbeat"
    BUTTON_PRESS = "button_press"
    SCORE_CHANGE = "score_change"
    SCORE_RESET = "score_reset"
    GAME_START = "game_start"
    GAME_END = "game_end"
    NEW_GAME = "new_game"
    SESSION_START = "session_start"
    SESSION_STOP = "session_stop"
    TIME_EXTEND = "time_extend"
    TABLE_STATUS = "table_status"
    DEVICE_ERROR = "device_error"


class DeviceEventStatus(str, enum.Enum):
    RECEIVED = "received"     # stored, not applied yet
    PROCESSED = "processed"   # applied to sessions/games
    REJECTED = "rejected"     # invalid; kept for inspection, never auto-deleted
    CONFLICT = "conflict"     # contradicts server state; needs reconciliation


class BilliardDevice(Base):
    """The single central controller (e.g. BILLIARD-CONTROLLER-01), not one per table."""
    __tablename__ = "billiard_devices"

    id: Mapped[int] = mapped_column(primary_key=True)
    client_id: Mapped[str] = mapped_column(String, nullable=False, index=True)
    device_id: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    status: Mapped[DeviceStatus] = mapped_column(
        enum_col(DeviceStatus), default=DeviceStatus.OFFLINE, nullable=False
    )
    api_key_hash: Mapped[str] = mapped_column(String(128), nullable=False)  # never store the raw key
    firmware_version: Mapped[str | None] = mapped_column(String(30), nullable=True)
    last_seen: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    # Highest device_seq fully applied; lets the server tell the device what to resend.
    last_applied_seq: Mapped[int] = mapped_column(BigInteger, default=0, server_default="0", nullable=False)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), onupdate=func.now())

    events = relationship("DeviceEvent", back_populates="device", cascade="all, delete-orphan")


class DeviceEvent(Base):
    __tablename__ = "device_events"

    id: Mapped[int] = mapped_column(primary_key=True)
    event_id: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)  # idempotency key
    device_pk: Mapped[int] = mapped_column(
        ForeignKey("billiard_devices.id", ondelete="CASCADE"), nullable=False, index=True
    )
    client_id: Mapped[str] = mapped_column(String, nullable=False, index=True)
    # SET NULL: events outlive a deleted table (audit trail).
    table_id: Mapped[int | None] = mapped_column(
        ForeignKey("billiard_tables.id", ondelete="SET NULL"), nullable=True, index=True
    )

    event_type: Mapped[DeviceEventType] = mapped_column(enum_col(DeviceEventType), nullable=False)
    # Ordering: device_seq is monotonic per device and survives reboot on the device.
    # Never order replayed events by timestamp: the ESP32 clock may be wrong offline.
    device_seq: Mapped[int] = mapped_column(BigInteger, nullable=False)
    device_timestamp: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    clock_synced: Mapped[bool | None] = mapped_column(Boolean, nullable=True)  # was NTP valid when stamped?
    received_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    processed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    status: Mapped[DeviceEventStatus] = mapped_column(
        enum_col(DeviceEventStatus), default=DeviceEventStatus.RECEIVED, nullable=False
    )
    error: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Local ids the device used while offline (LOCAL-S-..., LOCAL-G-...)
    local_session_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    local_game_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    payload: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    device = relationship("BilliardDevice", back_populates="events")

    __table_args__ = (
        UniqueConstraint("device_pk", "device_seq", name="uq_device_event_seq"),
        Index("ix_device_events_device_status", "device_pk", "status"),
    )


class DeviceLocalIdMap(Base):
    """LOCAL-S-20261004-0001 -> server session #1055 (kept until sync is complete and acked)."""
    __tablename__ = "device_local_id_map"

    id: Mapped[int] = mapped_column(primary_key=True)
    device_pk: Mapped[int] = mapped_column(
        ForeignKey("billiard_devices.id", ondelete="CASCADE"), nullable=False, index=True
    )
    kind: Mapped[str] = mapped_column(String(10), nullable=False)  # "session" | "game"
    local_id: Mapped[str] = mapped_column(String(64), nullable=False)
    session_id: Mapped[int | None] = mapped_column(ForeignKey("table_sessions.id", ondelete="CASCADE"), nullable=True)
    game_id: Mapped[int | None] = mapped_column(ForeignKey("table_games.id", ondelete="CASCADE"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (
        UniqueConstraint("device_pk", "kind", "local_id", name="uq_device_local_id"),
        CheckConstraint(
            "(kind = 'session' AND session_id IS NOT NULL AND game_id IS NULL) OR "
            "(kind = 'game' AND game_id IS NOT NULL AND session_id IS NULL)",
            name="ck_local_id_target_matches_kind",
        ),
    )