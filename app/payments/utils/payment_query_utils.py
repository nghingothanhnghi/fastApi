from sqlalchemy.orm import Query
from datetime import datetime
from typing import Optional

from app.payments.models.payment import PaymentTransaction


def apply_payment_filters(
    query: Query,
    status: Optional[str] = None,
    provider: Optional[str] = None,
    start_date: Optional[datetime] = None,
    end_date: Optional[datetime] = None,
    limit: Optional[int] = None,
    offset: Optional[int] = None,
) -> Query:
    """Apply common filters for payment queries."""
    if status:
        query = query.filter(PaymentTransaction.status == status)
    if provider:
        query = query.filter(PaymentTransaction.provider == provider)
    if start_date:
        query = query.filter(PaymentTransaction.created_at >= start_date)
    if end_date:
        query = query.filter(PaymentTransaction.created_at <= end_date)
    if offset:
        query = query.offset(offset)
    if limit:
        query = query.limit(limit)

    return query
