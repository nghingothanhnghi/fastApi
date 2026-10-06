# app/billiard/models/table.py
import enum
from datetime import datetime
from decimal import Decimal

from sqlalchemy import Boolean, DateTime, Index, Numeric, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base
from ._common import enum_col


class TableStatus(str, enum.Enum):
    AVAILABLE = "available"
    PLAYING = "playing"
    RESERVED = "reserved"
    MAINTENANCE = "maintenance"   # NEW


class BilliardTable(Base):
    __tablename__ = "billiard_tables"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(50), nullable=False)
    client_id: Mapped[str] = mapped_column(String, nullable=False, index=True)

    status: Mapped[TableStatus] = mapped_column(
        enum_col(TableStatus), default=TableStatus.AVAILABLE, nullable=False, index=True,
    )
    hourly_rate: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)

    # NEW: retire a table without deleting its history (sessions FK is RESTRICT)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, server_default="1", nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), onupdate=func.now())

    sessions = relationship("TableSession", back_populates="table", lazy="select")

    __table_args__ = (
        # NEW: DB-level backstop for the name check in table_service.create_table
        Index("uq_billiard_table_name_per_client", "client_id", "name", unique=True),
    )