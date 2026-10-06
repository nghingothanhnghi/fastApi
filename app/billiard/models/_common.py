# app/billiard/models/_common.py
from sqlalchemy import Enum


def enum_col(e, **kw):
    """Store enum *values* (lowercase strings), not member names."""
    return Enum(e, values_callable=lambda x: [m.value for m in x], **kw)