# app/core/i18n
import json
from pathlib import Path
from typing import Any

from .config import DEFAULT_LOCALE, SUPPORTED_LOCALES


class Translator:
    def __init__(self, locale: str = DEFAULT_LOCALE):
        self.locale = (
            locale
            if locale in SUPPORTED_LOCALES
            else DEFAULT_LOCALE
        )

        self._translations = self._load(self.locale)

    def _load(self, locale: str) -> dict[str, Any]:
        path = (
            Path(__file__).parent
            / "locales"
            / f"{locale}.json"
        )

        if not path.exists():
            return {}

        with path.open("r", encoding="utf-8") as file:
            return json.load(file)

    def get(self, key: str) -> Any:
        value: Any = self._translations

        for part in key.split("."):
            if not isinstance(value, dict):
                return None

            value = value.get(part)

            if value is None:
                return None

        return value

    def t(self, key: str, **kwargs: Any) -> str:
        value = self.get(key)

        if value is None:
            # Fall back to English
            if self.locale != DEFAULT_LOCALE:
                fallback = Translator(DEFAULT_LOCALE).get(key)

                if isinstance(fallback, str):
                    return self._format(fallback, kwargs)

            # Useful during development:
            # missing translation is visible immediately.
            return key

        if not isinstance(value, str):
            return key

        return self._format(value, kwargs)

    @staticmethod
    def _format(
        value: str,
        kwargs: dict[str, Any],
    ) -> str:
        if not kwargs:
            return value

        try:
            return value.format(**kwargs)
        except (KeyError, ValueError):
            return value