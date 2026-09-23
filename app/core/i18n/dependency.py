# app/core/i18n/dependency.py

from fastapi import Request

from .config import DEFAULT_LOCALE
from .translator import Translator


def get_locale(request: Request) -> str:
    return getattr(
        request.state,
        "locale",
        DEFAULT_LOCALE,
    )


def get_translator(request: Request) -> Translator:
    return Translator(get_locale(request))