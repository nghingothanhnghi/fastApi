from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class BankAccountCreate(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    bank_bin: str = Field(pattern=r"^\d{6}$", description="NAPAS BIN, 6 digits")
    bank_code: str | None = Field(default=None, max_length=20)
    account_no: str = Field(min_length=4, max_length=32, pattern=r"^[A-Za-z0-9]+$")
    account_name: str = Field(min_length=2, max_length=100)


class BankAccountRename(BaseModel):
    """Only the display name may change in place (e.g. typo fix)."""
    model_config = ConfigDict(str_strip_whitespace=True)

    account_name: str = Field(min_length=2, max_length=100)
    bank_code: str | None = Field(default=None, max_length=20)


class BankAccountOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    client_id: str  # tenant id is a UUID string, same as PaymentOrder.client_id
    bank_bin: str
    bank_code: str | None = None
    account_no: str
    account_name: str
    is_active: bool
    created_at: datetime


class BankAccountEventOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    account_id: int | None = None
    event_type: str
    actor_id: int | None = None
    data: dict[str, Any] | None = None
    created_at: datetime


class ParsedBankQrOut(BaseModel):
    """Result of reading a QR image. Nothing is saved; the user confirms first."""
    bank_bin: str
    account_no: str
    amount: int | None = None
    memo: str | None = None
