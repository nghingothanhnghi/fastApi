# app/billiard/models/session.py
from datetime import datetime
from decimal import Decimal

from sqlalchemy import (
    DateTime,
    Enum,
    ForeignKey,
    Numeric,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base

import enum


class SessionStatus(str, enum.Enum):
    ACTIVE = "active"
    COMPLETED = "completed"


class TableSession(Base):
    __tablename__ = "table_sessions"

    id: Mapped[int] = mapped_column(primary_key=True)

    table_id: Mapped[int] = mapped_column(
        ForeignKey("billiard_tables.id"),
        nullable=False,
        index=True,
    )

    start_time: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
    )

    end_time: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    status: Mapped[SessionStatus] = mapped_column(
        Enum(SessionStatus),
        default=SessionStatus.ACTIVE,
        nullable=False,
        index=True,
    )

    total_table_fee: Mapped[Decimal] = mapped_column(
        Numeric(12, 2),
        default=0,
        nullable=False,
    )

    total_product_fee: Mapped[Decimal] = mapped_column(
        Numeric(12, 2),
        default=0,
        nullable=False,
    )

    grand_total: Mapped[Decimal] = mapped_column(
        Numeric(12, 2),
        default=0,
        nullable=False,
    )

    table = relationship(
        "BilliardTable",
        back_populates="sessions",
    )

    items = relationship(
        "SessionItem",
        back_populates="session",
        cascade="all, delete-orphan",
        lazy="selectin",
    )