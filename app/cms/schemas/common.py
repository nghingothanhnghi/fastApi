# app/cms/schemas/common.py
# Shared building blocks for CMS schemas: partial-update null guard + typed delete responses.
from typing import ClassVar, FrozenSet

from pydantic import BaseModel, field_validator


class NonNullableUpdateMixin(BaseModel):
    """
    Base class for partial-update ("PATCH-style") schemas.

    Services apply updates with ``model_dump(exclude_unset=True)``: an omitted field is left
    untouched and an explicit ``null`` clears it. That is right for optional columns
    (excerpt, parent_id, ...) but would crash or corrupt columns that can never be NULL.
    List those in ``non_nullable_fields``: sending ``null`` for them is a 422 instead.
    (Validators only run for fields that were actually sent, so omitting them stays fine.)
    """

    non_nullable_fields: ClassVar[FrozenSet[str]] = frozenset()

    @field_validator("*", mode="before")
    @classmethod
    def _reject_explicit_null(cls, value, info):
        if value is None and info.field_name in cls.non_nullable_fields:
            raise ValueError("must not be null (omit the field to leave it unchanged)")
        return value


class DeleteOut(BaseModel):
    """Body of a successful DELETE for resources with no extra counters."""
    detail: str
