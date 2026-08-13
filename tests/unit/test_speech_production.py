"""Regression tests for clean-install speech loading."""

import json
import stat
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

import app.core.speech as speech


def test_module_import_does_not_require_vendored_whisper_tree():
    # Importing this module used to execute a hard-coded, gitignored file path.
    assert hasattr(speech, "SpeechRecognizer")


def test_missing_whisper_dependency_has_actionable_error(monkeypatch):
    monkeypatch.setattr(speech, "whisper", None)
    monkeypatch.setattr(speech, "torch", None)
    monkeypatch.setattr(
        speech, "_WHISPER_IMPORT_ERROR", ImportError("No module named whisper")
    )
    monkeypatch.setattr(speech, "_TORCH_IMPORT_ERROR", ImportError("No module named torch"))

    recognizer = speech.SpeechRecognizer(device="cpu")
    with pytest.raises(RuntimeError, match="openai-whisper") as error:
        recognizer.load_model()

    assert "pip install openai-whisper torch" in str(error.value)


def test_upstream_whisper_is_loaded_through_package_api(monkeypatch, tmp_path):
    model = Mock()
    whisper_module = Mock()
    whisper_module.load_model.return_value = model
    torch_module = Mock()
    torch_module.cuda.is_available.return_value = False
    monkeypatch.setattr(speech, "whisper", whisper_module)
    monkeypatch.setattr(speech, "torch", torch_module)
    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path))

    recognizer = speech.SpeechRecognizer(model="tiny", device="cpu")
    recognizer.load_model()

    whisper_module.load_model.assert_called_once()
    call = whisper_module.load_model.call_args
    assert call.args == ("tiny",)
    assert call.kwargs["device"] == "cpu"
    assert call.kwargs["download_root"] == str(tmp_path / "video-translator" / "whisper")
    assert (tmp_path / "video-translator" / "whisper").is_dir()


def test_whisper_model_directory_can_be_overridden(monkeypatch, tmp_path):
    model_dir = tmp_path / "large-volume" / "models"
    whisper_module = Mock()
    whisper_module.load_model.return_value = Mock()
    monkeypatch.setattr(speech, "whisper", whisper_module)
    monkeypatch.setattr(speech, "torch", Mock())
    monkeypatch.setenv("VIDEOTRANSLATOR_MODEL_DIR", str(model_dir))

    speech.SpeechRecognizer(model="base", device="cpu").load_model()

    assert whisper_module.load_model.call_args.kwargs["download_root"] == str(model_dir)
    assert model_dir.is_dir()


def _install_fake_ffmpeg(monkeypatch, captured_paths, *, duration="61"):
    class FakeOutput:
        def __init__(self, path):
            self.path = Path(path)

        def run(self, **_kwargs):
            captured_paths.append(self.path)
            self.path.write_bytes(b"pcm")

    class FakeInput:
        def output(self, path, **kwargs):
            assert kwargs == {"acodec": "pcm_s16le", "ac": 1, "ar": 16000}
            return FakeOutput(path)

    fake_ffmpeg = SimpleNamespace(
        probe=lambda _path: {
            "streams": [{"codec_type": "audio"}],
            "format": {"duration": duration},
        },
        input=lambda _path, **_kwargs: FakeInput(),
    )
    monkeypatch.setitem(sys.modules, "ffmpeg", fake_ffmpeg)


def test_segment_processing_uses_private_ephemeral_directories(monkeypatch, tmp_path):
    captured_paths = []
    _install_fake_ffmpeg(monkeypatch, captured_paths)
    recognizer = speech.SpeechRecognizer(device="cpu")
    monkeypatch.setattr(recognizer, "load_model", Mock())
    monkeypatch.setattr(
        recognizer,
        "transcribe",
        lambda *_args, **_kwargs: {
            "text": "ok",
            "segments": [{"start": 0.0, "end": 1.0, "text": "ok"}],
            "detected_language": "en",
        },
    )

    first = recognizer.process_segments(str(tmp_path / "same-name.mp3"), 30)
    first_parent = captured_paths[0].parent
    recognizer.process_segments(str(tmp_path / "same-name.mp3"), 30)
    second_parent = captured_paths[3].parent

    assert len(first["segments"]) == 3
    assert len(captured_paths) == 6
    assert first_parent != second_parent
    assert not first_parent.exists()
    assert not second_parent.exists()
    assert {path.suffix for path in captured_paths} == {".wav"}


def test_segment_processing_cancellation_never_returns_partial_success(monkeypatch):
    _install_fake_ffmpeg(monkeypatch, [])
    recognizer = speech.SpeechRecognizer(device="cpu")
    monkeypatch.setattr(recognizer, "load_model", Mock())
    recognizer.cancel()

    with pytest.raises(InterruptedError, match="已取消"):
        recognizer.process_segments("audio.wav", 30)


def test_transcription_cache_write_is_atomic_and_private(monkeypatch, tmp_path):
    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path))
    recognizer = speech.SpeechRecognizer(model="tiny", device="cpu")
    monkeypatch.setattr(recognizer, "_file_hash", Mock(return_value="audio-hash"))
    original = {"text": "safe", "segments": []}

    assert recognizer.cache_result("audio.wav", original) is True
    cache_path = (
        tmp_path
        / "video-translator"
        / "transcriptions"
        / "audio-hash_tiny.json"
    )
    assert json.loads(cache_path.read_text(encoding="utf-8")) == original
    assert stat.S_IMODE(cache_path.stat().st_mode) == 0o600

    assert recognizer.cache_result("audio.wav", {"invalid": object()}) is False
    assert json.loads(cache_path.read_text(encoding="utf-8")) == original
    assert list(cache_path.parent.glob("*.tmp")) == []
