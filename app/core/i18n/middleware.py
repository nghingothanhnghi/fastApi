# app/core/i18n/middleware.py

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request

from .config import DEFAULT_LOCALE, SUPPORTED_LOCALES


def normalize_locale(locale: str | None) -> str:
    if not locale:
        return DEFAULT_LOCALE

    locale = locale.strip().lower()

    # vi-VN -> vi
    # en-US -> en
    language = locale.split("-")[0].split("_")[0]

    if language in SUPPORTED_LOCALES:
        return language

    return DEFAULT_LOCALE


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

        if normalized in SUPPORTED_LOCALES:
            return normalized

    return DEFAULT_LOCALE


class I18nMiddleware(BaseHTTPMiddleware):
    async def dispatch(
        self,
        request: Request,
        call_next,
    ):
        accept_language = request.headers.get(
            "Accept-Language"
        )

        request.state.locale = parse_accept_language(
            accept_language
        )

        response = await call_next(request)

        # Tell clients which language was selected.
        response.headers["Content-Language"] = (
            request.state.locale
        )

        return response