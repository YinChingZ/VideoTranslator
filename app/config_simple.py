"""Deprecated compatibility import for the unified application config."""

from __future__ import annotations

import warnings

from .config import (
    APP_NAME,
    APP_VERSION,
    CONFIG_FILE,
    DEFAULT_BASE_DIR,
    LANGUAGE_CODES,
    LANGUAGES,
    TRANSLATION_PROVIDERS,
    WHISPER_MODELS,
    AppConfig,
    ConfigManager,
    get_config_manager,
)

warnings.warn(
    "app.config_simple is deprecated; import app.config instead",
    DeprecationWarning,
    stacklevel=2,
)

__all__ = [
    "APP_NAME",
    "APP_VERSION",
    "CONFIG_FILE",
    "DEFAULT_BASE_DIR",
    "LANGUAGES",
    "LANGUAGE_CODES",
    "TRANSLATION_PROVIDERS",
    "WHISPER_MODELS",
    "AppConfig",
    "ConfigManager",
    "get_config_manager",
]
