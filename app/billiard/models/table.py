# app/billiard/models/table.py
from decimal import Decimal
from sqlalchemy import Enum, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base

import enum


class TableStatus(str, enum.Enum):
    AVAILABLE = "available"
    PLAYING = "playing"
    RESERVED = "reserved"


class BilliardTable(Base):
    __tablename__ = "billiard_tables"

    id: Mapped[int] = mapped_column(primary_key=True)

    name: Mapped[str] = mapped_column(
        String(50),
        unique=True,
        index=True,
        nullable=False,
    )

    status: Mapped[TableStatus] = mapped_column(
        Enum(TableStatus),
        default=TableStatus.AVAILABLE,
        nullable=False,
        index=True,
    )

    hourly_rate: Mapped[Decimal] = mapped_column(
        Numeric(12, 2),
        nullable=False,
    )

    sessions = relationship(
        "TableSession",
        back_populates="table",
        lazy="selectin",
    )