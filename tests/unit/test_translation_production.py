"""Production-contract tests for external translation adapters."""

import tempfile
from pathlib import Path
from unittest.mock import Mock

import pytest

from app.core.translation import (
    DeepLTranslator,
    FallbackTranslator,
    GoogleTranslator,
    OpenAITranslator,
    QuotaExceededError,
    TranslationManager,
    TranslationRequest,
    TranslationResult,
)


def _response(status_code, body):
    response = Mock()
    response.status_code = status_code
    response.json.return_value = body
    response.raise_for_status.return_value = None
    response.text = str(body)
    return response


def test_openai_uses_responses_api_and_parses_native_output():
    translator = OpenAITranslator("test-key", model="test-model")
    translator.session.post = Mock(
        return_value=_response(
            200,
            {
                "id": "resp_123",
                "model": "test-model-2026-01-01",
                "output": [
                    {
                        "type": "message",
                        "role": "assistant",
                        "content": [
                            {"type": "output_text", "text": "你好，世界！"}
                        ],
                    }
                ],
                "usage": {"input_tokens": 10, "output_tokens": 5},
            },
        )
    )

    result = translator.translate_single(
        TranslationRequest("Hello, world!", "en", "zh-CN")
    )

    assert result.translated_text == "你好，世界！"
    assert result.service == "OpenAI"
    assert result.metadata["success"] is True
    assert result.metadata["fallback"] is False

    call = translator.session.post.call_args
    assert call.args[0] == "https://api.openai.com/v1/responses"
    assert call.kwargs["json"]["model"] == "test-model"
    assert call.kwargs["json"]["input"] == "Hello, world!"
    assert call.kwargs["headers"]["Authorization"] == "Bearer test-key"
    assert "messages" not in call.kwargs["json"]


def test_openai_maps_rate_limit_to_quota_error():
    translator = OpenAITranslator("test-key")
    translator.session.post = Mock(return_value=_response(429, {"error": {}}))

    with pytest.raises(QuotaExceededError):
        translator.translate_single(TranslationRequest("Hello", "en", "fr"))


def test_deepl_availability_does_not_make_a_network_probe():
    translator = DeepLTranslator("configured-key")
    translator.session.get = Mock(side_effect=AssertionError("unexpected network probe"))

    assert translator.is_available() is True
    translator.session.get.assert_not_called()


def test_deepl_batch_count_mismatch_is_a_failed_result_for_failover():
    translator = DeepLTranslator("configured-key")
    translator.session.post = Mock(
        return_value=_response(200, {"translations": [{"text": "un"}]})
    )

    results = translator.translate_batch(
        [
            TranslationRequest("one", "en", "fr"),
            TranslationRequest("two", "en", "fr"),
        ]
    )

    assert len(results) == 2
    assert all(result.metadata["success"] is False for result in results)


def test_google_batch_uses_v2_contract_and_decodes_text():
    translator = GoogleTranslator("google-key")
    translator.session.post = Mock(
        return_value=_response(
            200,
            {
                "data": {
                    "translations": [
                        {
                            "translatedText": "Bonjour &amp; bienvenue",
                            "detectedSourceLanguage": "en",
                        },
                        {
                            "translatedText": "Au revoir",
                            "detectedSourceLanguage": "en",
                        },
                    ]
                }
            },
        )
    )

    results = translator.translate_batch(
        [
            TranslationRequest("Hello & welcome", "auto", "fr-FR"),
            TranslationRequest("Goodbye", "auto", "fr-FR"),
        ]
    )

    assert [result.translated_text for result in results] == [
        "Bonjour & bienvenue",
        "Au revoir",
    ]
    assert all(result.metadata["success"] for result in results)

    call = translator.session.post.call_args
    assert call.args[0].endswith("/language/translate/v2")
    assert call.kwargs["params"] == {"key": "google-key"}
    assert call.kwargs["json"] == {
        "q": ["Hello & welcome", "Goodbye"],
        "target": "fr",
        "format": "text",
    }


def test_manager_registers_configured_services_and_marks_fallback_failure():
    with tempfile.TemporaryDirectory() as temp_dir:
        manager = TranslationManager(
            api_keys={"OpenAI": "openai-key", "GOOGLE": "google-key"},
            cache_path=str(Path(temp_dir) / "cache.db"),
            primary_service="openai",
        )
        assert set(manager.services) == {"OpenAI", "Google", "Fallback"}
        assert manager.service_priority[0] == "OpenAI"

    result = FallbackTranslator().translate_single(
        TranslationRequest("unchanged", "en", "zh-CN")
    )
    assert result.translated_text == "unchanged"
    assert result.confidence == 0.0
    assert result.metadata["success"] is False
    assert result.metadata["fallback"] is True
    assert result.metadata["error"] == "no_translation_service"


def test_manager_batch_retries_only_failed_items_with_next_provider(tmp_path):
    manager = TranslationManager(
        api_keys={"OPENAI": "openai-key", "google": "google-key"},
        cache_path=str(tmp_path / "cache.db"),
        primary_service="OPENAI",
    )

    openai = Mock()
    openai.is_available.return_value = True
    openai.translate_batch.return_value = [
        TranslationResult(
            original_text="one",
            translated_text="un",
            source_lang="en",
            target_lang="fr",
            confidence=0.9,
            service="OpenAI",
            metadata={"success": True, "fallback": False},
        ),
        TranslationResult(
            original_text="two",
            translated_text="two",
            source_lang="en",
            target_lang="fr",
            confidence=0.0,
            service="OpenAI",
            metadata={"success": False, "fallback": False},
        ),
    ]
    google = Mock()
    google.is_available.return_value = True
    google.translate_batch.return_value = [
        TranslationResult(
            original_text="two",
            translated_text="deux",
            source_lang="en",
            target_lang="fr",
            confidence=1.0,
            service="Google",
            metadata={"success": True, "fallback": False},
        )
    ]
    manager.services["OpenAI"] = openai
    manager.services["Google"] = google

    results = manager.translate_batch(
        ["one", "two"], "en", "fr", use_cache=False
    )

    assert [result.translated_text for result in results] == ["un", "deux"]
    assert [result.service for result in results] == ["OpenAI", "Google"]
    assert [request.text for request in openai.translate_batch.call_args.args[0]] == [
        "one",
        "two",
    ]
    assert [request.text for request in google.translate_batch.call_args.args[0]] == [
        "two"
    ]
