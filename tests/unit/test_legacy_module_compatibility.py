"""Keep retired module imports useful without reviving duplicate implementations."""

from __future__ import annotations

import importlib
import sys

import pytest

from app.config import AppConfig
from app.core import translation


def _deprecated_import(module_name: str):
    sys.modules.pop(module_name, None)
    with pytest.warns(DeprecationWarning):
        return importlib.import_module(module_name)


def test_translation_new_is_a_deprecated_reexport():
    legacy = _deprecated_import("app.core.translation_new")

    assert legacy.TranslationManager is translation.TranslationManager
    assert legacy.OpenAITranslator is translation.OpenAITranslator
    assert legacy.TranslationResult is translation.TranslationResult
    assert legacy.Translator is translation.Translator


def test_translation_original_adapts_legacy_manager_calls(tmp_path):
    legacy = _deprecated_import("app.core.translation_original")
    manager = legacy.Translator(
        primary_service="openai",
        fallback_services=["google"],
        cache_path=str(tmp_path / "legacy-cache.db"),
    )

    try:
        one = manager.translate("hello", "en", "zh", use_cache=False)
        many = manager.batch_translate(["one", "two"], "en", "fr", use_cache=False)

        assert one.metadata["success"] is False
        assert [result.original_text for result in many] == ["one", "two"]
        assert all(result.metadata["fallback"] for result in many)

        manager.add_terminology("subtitle", "字幕", "en-zh")
        assert manager.terminology.terminology["en-zh"]["subtitle"] == "字幕"
        manager.clear_cache()
    finally:
        manager.close()


def test_config_simple_is_a_deprecated_reexport():
    legacy = _deprecated_import("app.config_simple")

    assert legacy.AppConfig is AppConfig
    assert callable(legacy.get_config_manager)
