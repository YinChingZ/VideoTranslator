import sqlite3
from pathlib import Path

from app.core.translation import TranslationCache, TranslationManager, TranslationResult


def test_default_cache_honors_xdg_and_can_close(monkeypatch, tmp_path):
    cache_root = tmp_path / "custom-cache"
    monkeypatch.setenv("XDG_CACHE_HOME", str(cache_root))

    cache = TranslationCache()
    expected = cache_root / "video-translator" / "translation-cache.db"
    assert Path(cache.cache_path) == expected
    assert expected.exists()

    cache.close()
    cache.close()
    assert cache.conn is None


def test_manager_close_flushes_successful_translation(tmp_path):
    path = tmp_path / "nested" / "translations.db"
    manager = TranslationManager(cache_path=str(path))
    manager.cache.store(
        TranslationResult(
            original_text="hello",
            translated_text="你好",
            source_lang="en",
            target_lang="zh-CN",
            service="OpenAI",
            metadata={"success": True},
        )
    )

    manager.close()

    with TranslationCache(str(path)) as reopened:
        result = reopened.get("hello", "en", "zh-CN", "OpenAI")
        assert result is not None
        assert result.translated_text == "你好"


def test_corrupt_cache_metadata_is_treated_as_a_miss_and_removed(tmp_path):
    path = tmp_path / "translations.db"
    cache = TranslationCache(str(path))
    result = TranslationResult(
        original_text="hello",
        translated_text="bonjour",
        source_lang="en",
        target_lang="fr",
        service="DeepL",
        metadata={"success": True},
    )
    cache.store(result)
    key = cache._generate_key("hello", "en", "fr", "DeepL")
    cache._memory_cache.clear()
    with sqlite3.connect(path) as connection:
        connection.execute(
            "UPDATE translations SET metadata = ? WHERE hash = ?",
            ("{broken", key),
        )
        connection.commit()

    assert cache.get("hello", "en", "fr", "DeepL") is None
    with sqlite3.connect(path) as connection:
        assert connection.execute(
            "SELECT COUNT(*) FROM translations WHERE hash = ?", (key,)
        ).fetchone()[0] == 0
    cache.close()
