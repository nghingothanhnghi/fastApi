# app/payments/models/payment.py
from sqlalchemy import Column, Integer, String, Float, DateTime, ForeignKey, Enum, JSON, func
from sqlalchemy.orm import relationship
import enum
from app.database import Base


class PaymentStatus(str, enum.Enum):
    PENDING = "pending"
    COMPLETED = "completed"
    FAILED = "failed"
    REFUNDED = "refunded"


class PaymentTransaction(Base):
    __tablename__ = "payment_transactions"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    client_id = Column(String, nullable=False)

    provider = Column(String, nullable=False)  # e.g. "stripe", "paypal"
    amount = Column(Float, nullable=False)
    currency = Column(String, default="USD")
    status = Column(Enum(PaymentStatus), default=PaymentStatus.PENDING)
    reference_id = Column(String, unique=True, index=True)  # external payment id
    # ✅ Rename attribute but keep database column name
    extra_metadata = Column("extra_metadata", JSON, nullable=True)

    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    user = relationship("User", backref="payment_transactions")
