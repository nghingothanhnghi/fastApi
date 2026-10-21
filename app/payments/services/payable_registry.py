# app/payments/services/payable_registry.py
# The contract between the Payments module and a business module (billiard, a shop, ...).
#
# The business owns the object being paid and the amount. Payments owns everything about
# how it is paid. To make a business payable, write an adapter and register it once:
#
#     class MyShopOrderPayable:
#         source_type = "shop_order"
#         def load(self, db, source_id, user, *, lock=True): ...
#         def check_payable(self, obj): ...
#         def quote(self, obj) -> Quote: ...
#         def apply_state(self, db, obj, order): ...
#
#     payable_registry.register(MyShopOrderPayable())
#
# Payments then provides pay / split / cash change / VietQR / bank-feed confirmation /
# cancel / void / audit trail for it, under /payments/orders/{source_type}/{source_id}/...
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any, Optional, Protocol

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.user.models.user import User


@dataclass
class Quote:
    """What the business asks Payments to collect right now."""
    client_id: str                     # tenant that owns the object
    currency: str                      # 3-letter code, e.g. "VND"
    total: Decimal                     # full amount due for the object
    # Merged into every PaymentTransaction.extra_metadata. Put the keys that let a human
    # reconcile a payment with the business object (e.g. {"billiard_session_id": 42}).
    metadata: dict[str, Any] = field(default_factory=dict)


class PayableAdapter(Protocol):
    source_type: str

    def load(self, db: Session, source_id: str, user: Optional[User], *, lock: bool = True) -> Any:
        """Return the business object, or raise HTTPException(404).

        - user given: enforce the tenant check (404, not 403, for other tenants).
        - user None: a system caller (e.g. the bank feed); skip the tenant check.
        - lock: take a row lock so payments on the same object are serialized.
        """

    def check_payable(self, obj: Any) -> None:
        """Raise HTTPException(409) if the object cannot take a payment now (e.g. not finished yet)."""

    def quote(self, obj: Any) -> Quote:
        """Amount, currency and tenant to charge for."""

    def apply_state(self, db: Session, obj: Any, order: Any) -> None:
        """Mirror the order's payment state back onto the business object (no commit)."""


class PayableRegistry:
    def __init__(self) -> None:
        self._adapters: dict[str, PayableAdapter] = {}

    def register(self, adapter: PayableAdapter) -> None:
        self._adapters[adapter.source_type] = adapter

    def get(self, source_type: str) -> PayableAdapter:
        adapter = self._adapters.get(source_type)
        if adapter is None:
            raise HTTPException(404, f"Unknown payment source: {source_type}")
        return adapter

    def unregister(self, source_type: str) -> None:       # used by tests
        self._adapters.pop(source_type, None)


payable_registry = PayableRegistry()
