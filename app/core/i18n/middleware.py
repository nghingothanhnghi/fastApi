# app/core/i18n/middleware.py

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from app.core.logging_config import get_logger 

from .config import DEFAULT_LOCALE, SUPPORTED_LOCALES

logger = get_logger(__name__)

LANG_COOKIE_NAME = "lang"
LANG_QUERY_PARAM = "lang"


def normalize_locale(locale: str | None) -> str | None:
    """
    Normalize a raw locale string (e.g. "en-US", "vi_VN") to one of our
    supported language codes, or None if it doesn't match anything we
    support. Returning None (instead of always falling back to
    DEFAULT_LOCALE) lets callers that iterate over multiple candidates
    (see parse_accept_language) correctly skip unsupported entries instead
    of short-circuiting on the first one.
    """
    if not locale:
        return None

    locale = locale.strip().lower()

    # vi-VN -> vi
    # en-US -> en
    language = locale.split("-")[0].split("_")[0]

    if language in SUPPORTED_LOCALES:
        return language

    return None


def parse_accept_language(header: str | None) -> str:
    if not header:
        return DEFAULT_LOCALE

    languages: list[tuple[str, float]] = []

    for item in header.split(","):
        parts = item.strip().split(";")

        locale = parts[0].strip()

        quality = 1.0

        for part in parts[1:]:
            part = part.strip()

            if part.startswith("q="):
                try:
                    quality = float(part[2:])
                except ValueError:
                    quality = 0.0

        languages.append((locale, quality))

    languages.sort(
        key=lambda item: item[1],
        reverse=True,
    )

    for locale, _ in languages:
        normalized = normalize_locale(locale)

        if normalized is not None:
            return normalized

    return DEFAULT_LOCALE


def resolve_locale(request: Request) -> str:
    """
    Resolve the locale for this request, in priority order:
      1. Explicit cookie (persists a user's choice across every request)
      2. Explicit ?lang= query param (manual/one-off override)
      3. Accept-Language header (browser default)
      4. DEFAULT_LOCALE (final fallback)
    """
    # 1. Cookie
    cookie_locale = normalize_locale(request.cookies.get(LANG_COOKIE_NAME))
    if cookie_locale is not None:
        return cookie_locale

    # 2. Query param
    query_locale = normalize_locale(request.query_params.get(LANG_QUERY_PARAM))
    if query_locale is not None:
        return query_locale

    # 3. Accept-Language header (falls back to DEFAULT_LOCALE internally)
    return parse_accept_language(request.headers.get("Accept-Language"))


class I18nMiddleware(BaseHTTPMiddleware):
    async def dispatch(
        self,
        request: Request,
        call_next,
    ):
        request.state.locale = resolve_locale(request)

        logger.info( 
            "[i18n] path=%r cookie=%r accept-language=%r resolved=%r", 
            request.url.path, request.cookies.get(LANG_COOKIE_NAME), 
            request.headers.get("Accept-Language"), 
            request.state.locale, 
        )

        response = await call_next(request)

        # Tell clients which language was selected.
        response.headers["Content-Language"] = (
            request.state.locale
        )

        return response