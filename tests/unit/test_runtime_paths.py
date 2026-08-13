"""Contracts for centralized, user-writable runtime paths."""

from pathlib import Path

from app.utils.logger import cleanup_old_logs, get_log_path
from app.utils.paths import (
    get_cache_dir,
    get_checkpoint_dir,
    get_config_dir,
    get_state_dir,
    get_transcription_cache_dir,
    get_whisper_model_dir,
)


def test_explicit_runtime_path_overrides_are_shared(monkeypatch, tmp_path):
    cache = tmp_path / "cache root"
    state = tmp_path / "state root"
    model = tmp_path / "model root"
    config = tmp_path / "config root"
    checkpoints = tmp_path / "checkpoint root"
    monkeypatch.setenv("VIDEOTRANSLATOR_CACHE_DIR", str(cache))
    monkeypatch.setenv("VIDEOTRANSLATOR_STATE_DIR", str(state))
    monkeypatch.setenv("VIDEOTRANSLATOR_MODEL_DIR", str(model))
    monkeypatch.setenv("VIDEOTRANSLATOR_CONFIG_DIR", str(config))
    monkeypatch.setenv("VIDEOTRANSLATOR_CHECKPOINT_DIR", str(checkpoints))

    assert get_cache_dir() == cache
    assert get_state_dir() == state
    assert get_whisper_model_dir() == model
    assert get_config_dir() == config
    assert get_checkpoint_dir() == checkpoints
    assert get_transcription_cache_dir() == cache / "transcriptions"
    assert get_log_path().parent == state / "logs"


def test_log_cleanup_uses_state_directory(monkeypatch, tmp_path):
    monkeypatch.setenv("VIDEOTRANSLATOR_STATE_DIR", str(tmp_path))
    log_dir = tmp_path / "logs"
    log_dir.mkdir()
    stale = log_dir / "videotranslator_2000-01-01.log"
    stale.write_text("old", encoding="utf-8")

    cleanup_old_logs(days=7)

    assert not stale.exists()
    assert not (Path.home() / ".videotranslator" / "logs" / stale.name).exists()
