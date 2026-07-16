# app/cms/utils/slugify.py
# Small, dependency-free slug helpers shared by categories, tags, and posts.
import re
import unicodedata
from typing import Callable


def slugify(value: str) -> str:
    """Convert a string into a URL-friendly, lowercase, hyphenated slug."""
    value = unicodedata.normalize("NFKD", value or "").encode("ascii", "ignore").decode("ascii")
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
