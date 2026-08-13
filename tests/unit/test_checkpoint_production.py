import json
import os
from pathlib import Path

from app.utils.checkpoint import CheckpointManager

SETTINGS = {
    "source_language": "auto",
    "target_language": "zh-CN",
    "whisper_model": "base",
    "translation_provider": "openai",
}


def test_default_checkpoint_path_uses_platform_state_override(tmp_path, monkeypatch):
    state_root = tmp_path / "application state"
    monkeypatch.setenv("VIDEOTRANSLATOR_STATE_DIR", str(state_root))

    manager = CheckpointManager()

    assert manager.project_dir == state_root / "checkpoints"
    assert manager.project_dir.is_dir()


def test_checkpoint_is_bound_to_processing_settings_and_artifacts(tmp_path):
    video = tmp_path / "video.mp4"
    audio = tmp_path / "audio.wav"
    video.write_bytes(b"video")
    audio.write_bytes(b"audio")
    manager = CheckpointManager(str(tmp_path / "checkpoints"))

    assert manager.save_checkpoint(
        str(video),
        "audio_extraction",
        {"audio_path": str(audio)},
        **SETTINGS,
    )
    assert manager.can_resume(str(video), **SETTINGS)
    assert not manager.can_resume(
        str(video),
        **{**SETTINGS, "target_language": "ja"},
    )

    audio.unlink()
    assert not manager.can_resume(str(video), **SETTINGS)


def test_checkpoint_write_is_private_atomic_json_and_success_can_clear(tmp_path):
    video = tmp_path / "clip.mp4"
    video.write_bytes(b"content")
    manager = CheckpointManager(str(tmp_path / "checkpoints"))

    assert manager.save_checkpoint(
        str(video),
        "speech_recognition",
        {"recognition_result": {"segments": []}},
        **SETTINGS,
    )

    checkpoint_file = manager._get_checkpoint_file(str(video))
    payload = json.loads(checkpoint_file.read_text(encoding="utf-8"))
    assert payload["version"].startswith("2.")
    assert payload["target_language"] == "zh-cn"
    if os.name != "nt":
        assert checkpoint_file.stat().st_mode & 0o777 == 0o600
    assert not list(checkpoint_file.parent.glob("*.tmp"))

    assert manager.clear_checkpoint(str(video))
    assert not checkpoint_file.exists()


def test_relative_and_absolute_video_paths_share_one_checkpoint(tmp_path, monkeypatch):
    video = tmp_path / "same.mp4"
    video.write_bytes(b"same")
    manager = CheckpointManager(str(tmp_path / "checkpoints"))
    monkeypatch.chdir(tmp_path)

    relative = Path("same.mp4")
    assert manager.save_checkpoint(
        str(relative),
        "speech_recognition",
        {"recognition_result": {"segments": []}},
        **SETTINGS,
    )
    assert manager.load_checkpoint(str(video), **SETTINGS) is not None
