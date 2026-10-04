# app/billiard/models/table.py
import enum
from datetime import datetime
from decimal import Decimal

from sqlalchemy import DateTime, Enum, Numeric, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class TableStatus(str, enum.Enum):
    AVAILABLE = "available"
    PLAYING = "playing"
    RESERVED = "reserved"


class BilliardTable(Base):
    __tablename__ = "billiard_tables"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(50), nullable=False)

    # Same tenant convention as HydroDevice / VisionPlant
    client_id: Mapped[str] = mapped_column(String, nullable=False, index=True)

    status: Mapped[TableStatus] = mapped_column(
        Enum(TableStatus, values_callable=lambda e: [m.value for m in e]),
        default=TableStatus.AVAILABLE, nullable=False, index=True,
    )
    hourly_rate: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    sessions = relationship("TableSession", back_populates="table", lazy="select")