"""Compatibility adapter for the retired pre-2.0 translation module.

New code must use :mod:`app.core.translation`.  The old implementation was a
second, stale set of provider clients (including obsolete API contracts), so
only its import surface and manager call shape are retained here.
"""

from __future__ import annotations

import warnings
from collections.abc import Iterable
from typing import Any

from .translation import (
    DEFAULT_BACKOFF_FACTOR,
    DEFAULT_BATCH_SIZE,
    DEFAULT_CACHE_SIZE,
    DEFAULT_RETRY_COUNT,
    DEFAULT_TIMEOUT,
    DeepLTranslator,
    GoogleTranslator,
    OpenAITranslator,
    QuotaExceededError,
    ServiceUnavailableError,
    TranslationCache,
    TranslationError,
    TranslationManager,
    TranslationRequest,
    TranslationResult,
    TranslatorInterface,
)

warnings.warn(
    "app.core.translation_original is deprecated; import app.core.translation instead",
    DeprecationWarning,
    stacklevel=2,
)


class TerminologyManager:
    """Adapt the former terminology method signatures to the active manager."""

    def __init__(self, terminology_file: str | None = None):
        from .translation import TerminologyManager as ActiveTerminologyManager

        self._manager = ActiveTerminologyManager()
        if terminology_file:
            self._load(terminology_file)

    @property
    def terminology(self) -> dict[str, dict[str, str]]:
        return self._manager.terminology

    def _load(self, file_path: str) -> None:
        import json

        with open(file_path, encoding="utf-8") as stream:
            loaded = json.load(stream)
        if not isinstance(loaded, dict):
            raise ValueError("terminology file must contain an object")
        self._manager.terminology = loaded

    def add_term(self, source_term: str, target_term: str, lang_pair: str) -> None:
        source_lang, separator, target_lang = lang_pair.partition("-")
        if not separator or not source_lang or not target_lang:
            raise ValueError("lang_pair must use the '<source>-<target>' form")
        self._manager.add_term(source_lang, target_lang, source_term, target_term)

    def get_translation(self, term: str, lang_pair: str) -> str | None:
        return self.terminology.get(lang_pair, {}).get(term)

    def apply_terminology(
        self,
        text: str,
        translated_text: str,
        source_lang: str,
        target_lang: str,
    ) -> str:
        del text
        return self._manager.apply_terminology(
            translated_text,
            source_lang,
            target_lang,
        )

    def save_to_file(self, file_path: str) -> None:
        import json

        with open(file_path, "w", encoding="utf-8") as stream:
            json.dump(self.terminology, stream, ensure_ascii=False, indent=2)


class Translator(TranslationManager):
    """Translate legacy manager calls through the maintained implementation.

    ``service`` and extra provider kwargs are accepted for source
    compatibility.  Provider selection is now governed by the manager's
    failover order, so an explicit service is temporarily promoted for that
    call instead of selecting a separate legacy client.
    """

    def __init__(
        self,
        primary_service: str = "openai",
        fallback_services: Iterable[str] | None = None,
        api_keys: dict[str, str] | None = None,
        cache_path: str | None = None,
    ) -> None:
        self.primary_service = primary_service.lower()
        self.fallback_services = [name.lower() for name in fallback_services or ()]
        super().__init__(
            api_keys=api_keys,
            cache_path=cache_path,
            primary_service=primary_service,
        )

    def _promote_service(self, service: str | None) -> list[str] | None:
        if not service:
            return None
        normalized = service.strip().lower()
        canonical = next(
            (name for name in self.service_priority if name.lower() == normalized),
            None,
        )
        if canonical is None:
            raise TranslationError(f"Translation service is not configured: {service}")
        previous = list(self.service_priority)
        self.service_priority = [canonical, *(
            name for name in self.service_priority if name != canonical
        )]
        return previous

    def translate(
        self,
        text: str,
        source_lang: str,
        target_lang: str,
        service: str | None = None,
        use_cache: bool = True,
        apply_terminology: bool = True,
        **kwargs: Any,
    ) -> TranslationResult:
        del apply_terminology, kwargs
        previous = self._promote_service(service)
        try:
            return super().translate(text, source_lang, target_lang, use_cache)
        finally:
            if previous is not None:
                self.service_priority = previous

    def batch_translate(
        self,
        texts: list[str],
        source_lang: str,
        target_lang: str,
        service: str | None = None,
        use_cache: bool = True,
        apply_terminology: bool = True,
        **kwargs: Any,
    ) -> list[TranslationResult]:
        del apply_terminology, kwargs
        previous = self._promote_service(service)
        try:
            return super().translate_batch(
                texts,
                source_lang,
                target_lang,
                use_cache,
            )
        finally:
            if previous is not None:
                self.service_priority = previous

    def clear_cache(self) -> None:
        """Clear persistent and in-memory entries through supported cache APIs."""
        self.cache.clear()

    def add_terminology(
        self,
        source_term: str,
        target_term: str,
        lang_pair: str,
    ) -> None:
        source_lang, separator, target_lang = lang_pair.partition("-")
        if not separator or not source_lang or not target_lang:
            raise ValueError("lang_pair must use the '<source>-<target>' form")
        self.terminology.add_term(
            source_lang,
            target_lang,
            source_term,
            target_term,
        )

    def set_terminology_file(self, file_path: str) -> None:
        adapter = TerminologyManager(file_path)
        self.terminology.terminology = adapter.terminology

    def detect_language(self, text: str) -> dict[str, float]:
        del text
        return {}


__all__ = [
    "DEFAULT_BACKOFF_FACTOR",
    "DEFAULT_BATCH_SIZE",
    "DEFAULT_CACHE_SIZE",
    "DEFAULT_RETRY_COUNT",
    "DEFAULT_TIMEOUT",
    "DeepLTranslator",
    "GoogleTranslator",
    "OpenAITranslator",
    "QuotaExceededError",
    "ServiceUnavailableError",
    "TerminologyManager",
    "TranslationCache",
    "TranslationError",
    "TranslationManager",
    "TranslationRequest",
    "TranslationResult",
    "Translator",
    "TranslatorInterface",
]
