# app/cms/utils/slugify.py
# Small, dependency-free slug helpers shared by categories, tags, and posts.
import re
import unicodedata
from typing import Callable, TypeVar

from fastapi import HTTPException, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

T = TypeVar("T")


def slugify(value: str) -> str:
    """Convert a string into a URL-friendly, lowercase, hyphenated slug."""
    # "đ"/"Đ" have no NFKD decomposition and would otherwise be dropped entirely.
    value = (value or "").replace("đ", "d").replace("Đ", "D")
    value = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode("ascii")
    value = re.sub(r"[^\w\s-]", "", value).strip().lower()
    value = re.sub(r"[-\s]+", "-", value)
    return value or "n-a"


def make_unique_slug(base_slug: str, exists_fn: Callable[[str], bool]) -> str:
    """
    Given a base slug and a callable exists_fn(slug) -> bool,
    append -2, -3, ... until a free slug is found.
    """
    slug = base_slug
    counter = 2
    while exists_fn(slug):
        slug = f"{base_slug}-{counter}"
        counter += 1
    return slug


def _is_slug_conflict(exc: IntegrityError) -> bool:
    """True when the unique violation is on a slug column/index (SQLite and PostgreSQL wording)."""
    return "slug" in str(getattr(exc, "orig", exc)).lower()


def run_with_slug_retry(db: Session, operation: Callable[[], T], attempts: int = 5) -> T:
    """
    Run `operation` (which picks a slug, mutates, and COMMITS) and retry it if two requests
    race for the same slug.

    make_unique_slug() is check-then-insert, so a concurrent request can take the slug between
    the check and the commit. The DB unique index then rejects the loser with an IntegrityError;
    we roll back and re-run `operation`, which re-checks and picks the next free slug.
    `operation` must therefore be safe to run again from scratch (re-read rows, rebuild objects).

    Any other integrity violation (duplicate tag name, taken menu location, ...) becomes a 409.
    """
    for attempt in range(1, attempts + 1):
        try:
            return operation()
        except IntegrityError as exc:
            db.rollback()
            if not _is_slug_conflict(exc):
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail="A record with the same unique value already exists",
                )
            if attempt == attempts:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail="Could not allocate a unique slug, please retry",
                )
