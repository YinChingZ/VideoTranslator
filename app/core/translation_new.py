"""Deprecated import compatibility for :mod:`app.core.translation`.

The experimental implementation that used to live in this module diverged
from the production pipeline.  Keeping a second copy made provider fixes and
cache guarantees easy to apply to the wrong file, so this module now exposes
the single maintained implementation.
"""

from __future__ import annotations

import warnings

from .translation import (
    DEFAULT_BACKOFF_FACTOR,
    DEFAULT_BATCH_SIZE,
    DEFAULT_CACHE_SIZE,
    DEFAULT_RETRY_COUNT,
    DEFAULT_TIMEOUT,
    DeepLTranslator,
    FallbackTranslator,
    GoogleTranslator,
    OpenAITranslator,
    QuotaExceededError,
    ServiceUnavailableError,
    TerminologyManager,
    TranslationCache,
    TranslationError,
    TranslationManager,
    TranslationRequest,
    TranslationResult,
    Translator,
    TranslatorInterface,
)

warnings.warn(
    "app.core.translation_new is deprecated; import app.core.translation instead",
    DeprecationWarning,
    stacklevel=2,
)

__all__ = [
    "DEFAULT_BACKOFF_FACTOR",
    "DEFAULT_BATCH_SIZE",
    "DEFAULT_CACHE_SIZE",
    "DEFAULT_RETRY_COUNT",
    "DEFAULT_TIMEOUT",
    "DeepLTranslator",
    "FallbackTranslator",
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
