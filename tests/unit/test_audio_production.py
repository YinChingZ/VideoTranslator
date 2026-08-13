"""Regression tests for modern, streamed audio preprocessing."""

import sys
from contextlib import contextmanager
from pathlib import Path
from types import ModuleType
from unittest.mock import Mock

import numpy as np
import pytest

from app.core.audio import AudioProcessingError, AudioProcessor


def test_preprocess_streams_chunks_to_soundfile(monkeypatch, tmp_path):
    processor = AudioProcessor(temp_dir=tmp_path)
    source = tmp_path / "source.wav"
    source.write_bytes(b"placeholder")
    destination = tmp_path / "processed.wav"

    @contextmanager
    def fake_chunks(*_args, **_kwargs):
        yield iter(
            [
                (np.array([0.1, -0.1], dtype=np.float32), 16000),
                (np.array([0.2], dtype=np.float32), 16000),
            ]
        )

    writer = Mock()

    class FakeSoundFile:
        def __init__(self, path, **_kwargs):
            self.path = Path(path)

        def __enter__(self):
            return writer

        def __exit__(self, *_args):
            self.path.write_bytes(b"encoded audio")

    soundfile = ModuleType("soundfile")
    soundfile.SoundFile = FakeSoundFile

    monkeypatch.setattr(processor, "_process_audio_chunks", fake_chunks)
    monkeypatch.setitem(sys.modules, "soundfile", soundfile)

    result = processor.preprocess_audio_for_speech(
        source,
        destination,
        noise_reduction=False,
        normalize=False,
    )

    assert result == destination
    assert writer.write.call_count == 2
    first_chunk = writer.write.call_args_list[0].args[0]
    assert first_chunk.dtype == np.float32


def test_chunk_context_cleanup_is_safe_if_open_fails(monkeypatch, tmp_path):
    processor = AudioProcessor(temp_dir=tmp_path)

    def fail_open(*_args, **_kwargs):
        raise RuntimeError("cannot open")

    soundfile = ModuleType("soundfile")
    soundfile.SoundFile = fail_open
    monkeypatch.setitem(sys.modules, "soundfile", soundfile)

    try:
        with processor._process_audio_chunks(tmp_path / "missing.wav", 16000):
            pass
    except RuntimeError as error:
        assert str(error) == "cannot open"
    else:  # pragma: no cover - defensive assertion
        raise AssertionError("expected the mocked open failure")


def test_preprocess_failure_preserves_existing_destination(monkeypatch, tmp_path):
    processor = AudioProcessor(temp_dir=tmp_path / "temporary")
    source = tmp_path / "source.wav"
    source.write_bytes(b"source")
    destination = tmp_path / "processed.wav"
    destination.write_bytes(b"keep-existing")

    @contextmanager
    def failing_chunks(*_args, **_kwargs):
        raise RuntimeError("decoder failed")
        yield  # pragma: no cover - makes this a contextmanager generator

    monkeypatch.setattr(processor, "_process_audio_chunks", failing_chunks)

    with pytest.raises(AudioProcessingError, match="decoder failed"):
        processor.preprocess_audio_for_speech(source, destination)

    assert destination.read_bytes() == b"keep-existing"
    assert list(tmp_path.glob(".videotranslator-audio-*")) == []


def test_extract_failure_preserves_existing_destination(monkeypatch, tmp_path):
    processor = AudioProcessor(temp_dir=tmp_path / "temporary")
    source = tmp_path / "source.mp4"
    source.write_bytes(b"source")
    destination = tmp_path / "audio.wav"
    destination.write_bytes(b"keep-existing")

    monkeypatch.setattr(
        "app.core.audio.ffmpeg.run",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(RuntimeError("ffmpeg failed")),
    )

    with pytest.raises(AudioProcessingError, match="ffmpeg failed"):
        processor.extract_audio_from_video(source, destination)

    assert destination.read_bytes() == b"keep-existing"
    assert list(tmp_path.glob(".videotranslator-audio-*")) == []
