"""Production contract tests for the active four-stage processing worker."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any
from unittest.mock import Mock

import pytest
from PyQt5.QtCore import QObject, pyqtSignal

from app.core.translation import TranslationResult
from app.gui.improved_processing import ImprovedProcessingWorker
from app.gui.processing import ProcessingWidget
from app.utils.checkpoint import CheckpointManager


@dataclass
class PipelineHarness:
    worker: ImprovedProcessingWorker
    audio: Mock
    speech: Mock
    translator: Mock
    subtitle: Mock
    checkpoints: CheckpointManager
    video: Path
    audio_file: Path
    subtitle_file: Path


def make_harness(
    tmp_path: Path,
    *,
    target_language: str = "zh-CN",
    provider: str = "OpenAI",
) -> PipelineHarness:
    video = tmp_path / "movie.mp4"
    audio_file = tmp_path / "movie.wav"
    subtitle_file = tmp_path / "movie.srt"
    if not video.exists():
        video.write_bytes(b"video")
    if not audio_file.exists():
        audio_file.write_bytes(b"audio")

    audio = Mock()
    audio.extract_audio_from_video.return_value = audio_file
    speech = Mock()
    speech.transcribe.return_value = {
        "text": "Hello world",
        "segments": [
            {"start": 0.25, "end": 1.5, "text": "Hello"},
            {"start": 1.5, "end": 3.0, "text": "world"},
        ],
    }
    translator = Mock()
    translator.translate.side_effect = [
        TranslationResult(
            "Hello",
            "你好",
            "en",
            target_language,
            service="OpenAI",
            metadata={"success": True, "fallback": False},
        ),
        TranslationResult(
            "world",
            "世界",
            "en",
            target_language,
            service="OpenAI",
            metadata={"success": True, "fallback": False},
        ),
    ]
    subtitle = Mock()

    def save_subtitle(*args: Any, **kwargs: Any) -> str:
        del args, kwargs
        subtitle_file.write_text("translated", encoding="utf-8")
        return str(subtitle_file)

    subtitle.save_to_file.side_effect = save_subtitle
    checkpoints = CheckpointManager(str(tmp_path / "checkpoints"))
    worker = ImprovedProcessingWorker(
        str(video),
        "en-US",
        target_language,
        {
            "whisper_model": "Small",
            "translation_provider": provider,
            "api_keys": {"OpenAI": "secret"},
        },
        audio_processor=audio,
        speech_recognizer=speech,
        translator=translator,
        subtitle_processor=subtitle,
        checkpoint_manager=checkpoints,
    )
    return PipelineHarness(
        worker,
        audio,
        speech,
        translator,
        subtitle,
        checkpoints,
        video,
        audio_file,
        subtitle_file,
    )


def capture_terminals(worker: ImprovedProcessingWorker) -> dict[str, list[Any]]:
    captured: dict[str, list[Any]] = {
        "finished": [],
        "error": [],
        "cancelled": [],
    }
    worker.finished.connect(captured["finished"].append)
    worker.error.connect(captured["error"].append)
    worker.cancelled.connect(lambda: captured["cancelled"].append(True))
    return captured


def assert_one_terminal(captured: dict[str, list[Any]], expected: str) -> None:
    assert {key: len(values) for key, values in captured.items()} == {
        "finished": int(expected == "finished"),
        "error": int(expected == "error"),
        "cancelled": int(expected == "cancelled"),
    }


def test_pipeline_success_maps_segments_and_clears_checkpoint(tmp_path):
    harness = make_harness(tmp_path)
    captured = capture_terminals(harness.worker)

    harness.worker.run()

    assert_one_terminal(captured, "finished")
    result = captured["finished"][0]
    assert result["status"] == "completed"
    assert result["video_path"] == str(harness.video.resolve())
    assert result["segments"] == [
        {
            "start": 0.25,
            "end": 1.5,
            "original_text": "Hello",
            "translated_text": "你好",
        },
        {
            "start": 1.5,
            "end": 3.0,
            "original_text": "world",
            "translated_text": "世界",
        },
    ]
    harness.speech.transcribe.assert_called_once_with(
        str(harness.audio_file), language="en"
    )
    assert harness.translator.translate.call_count == 2
    harness.translator.close.assert_called_once_with()
    harness.audio.cleanup.assert_called_once_with()
    created = harness.subtitle.create_from_segments.call_args.args[0]
    assert created[0] == {
        "start": 0.25,
        "end": 1.5,
        "original_text": "Hello",
        "translated_text": "你好",
    }
    harness.subtitle.save_to_file.assert_called_once()
    assert harness.checkpoints.load_checkpoint(
        str(harness.video), **harness.worker.processing_settings
    ) is None


def test_failed_translation_is_error_not_original_text_success(tmp_path):
    harness = make_harness(tmp_path)
    harness.translator.translate.side_effect = None
    harness.translator.translate.return_value = TranslationResult(
        "Hello",
        "Hello",
        "en",
        "zh-CN",
        service="fallback",
        metadata={"success": False, "fallback": True},
    )
    captured = capture_terminals(harness.worker)

    harness.worker.run()

    assert_one_terminal(captured, "error")
    assert "原文不会被伪装成译文" in captured["error"][0]
    harness.subtitle.create_from_segments.assert_not_called()
    checkpoint = harness.checkpoints.load_checkpoint(
        str(harness.video), **harness.worker.processing_settings
    )
    assert checkpoint is not None
    assert checkpoint.completed_stages == ["audio_extraction", "speech_recognition"]


def test_cancellation_emits_only_cancelled_and_preserves_last_stage(tmp_path):
    harness = make_harness(tmp_path)
    captured = capture_terminals(harness.worker)

    def cancel_after_recognition(*args: Any, **kwargs: Any) -> dict[str, Any]:
        del args, kwargs
        result = {
            "segments": [{"start": 0.0, "end": 1.0, "text": "stop"}],
        }
        harness.worker.cancel_requested.set()
        return result

    harness.speech.transcribe.side_effect = cancel_after_recognition
    harness.worker.run()

    assert_one_terminal(captured, "cancelled")
    harness.translator.translate.assert_not_called()
    checkpoint = harness.checkpoints.load_checkpoint(
        str(harness.video), **harness.worker.processing_settings
    )
    assert checkpoint is not None
    # Cancellation at the stage boundary means recognition never became a
    # completed durable stage. Only the previous extraction is resumable.
    assert checkpoint.completed_stages == ["audio_extraction"]


def test_resume_same_settings_reuses_snapshot_and_changed_settings_restart(tmp_path):
    first = make_harness(tmp_path)
    settings = first.worker.processing_settings
    recognition = first.speech.transcribe.return_value
    translation = {
        "original_segments": recognition["segments"],
        "translated_texts": ["你好", "世界"],
        "services": ["OpenAI", "OpenAI"],
    }
    assert first.checkpoints.save_checkpoint(
        str(first.video),
        "audio_extraction",
        {"audio_path": str(first.audio_file)},
        **settings,
    )
    assert first.checkpoints.save_checkpoint(
        str(first.video),
        "speech_recognition",
        {"recognition_result": recognition},
        **settings,
    )
    assert first.checkpoints.save_checkpoint(
        str(first.video),
        "text_translation",
        {"translation_result": translation},
        **settings,
    )

    same = make_harness(tmp_path)
    captured = capture_terminals(same.worker)
    same.worker.run()

    assert_one_terminal(captured, "finished")
    same.audio.extract_audio_from_video.assert_not_called()
    same.speech.transcribe.assert_not_called()
    same.translator.translate.assert_not_called()
    assert captured["finished"][0]["segments"][0]["original_text"] == "Hello"

    # Recreate a checkpoint, then change a single fingerprint setting. No
    # stage may be reused even though the artifacts still exist.
    changed_seed = make_harness(tmp_path)
    assert changed_seed.checkpoints.save_checkpoint(
        str(changed_seed.video),
        "audio_extraction",
        {"audio_path": str(changed_seed.audio_file)},
        **changed_seed.worker.processing_settings,
    )
    changed = make_harness(tmp_path, target_language="ja")
    changed_captured = capture_terminals(changed.worker)
    changed.worker.run()

    assert_one_terminal(changed_captured, "finished")
    changed.audio.extract_audio_from_video.assert_called_once()
    changed.speech.transcribe.assert_called_once()
    assert changed.translator.translate.call_count == 2


def test_every_stage_save_uses_same_processing_fingerprint(tmp_path):
    harness = make_harness(tmp_path)
    calls: list[tuple[str, dict[str, str]]] = []
    original_save = harness.checkpoints.save_checkpoint

    def recording_save(
        video_path: str,
        stage: str,
        stage_data: dict[str, Any],
        **settings: str,
    ) -> bool:
        calls.append((stage, settings))
        return original_save(video_path, stage, stage_data, **settings)

    harness.checkpoints.save_checkpoint = recording_save  # type: ignore[method-assign]
    harness.worker.run()

    assert [stage for stage, _ in calls] == list(ImprovedProcessingWorker.STAGES)
    assert all(settings == harness.worker.processing_settings for _, settings in calls)


def test_worker_emits_terminal_only_after_cleanup(tmp_path):
    harness = make_harness(tmp_path)
    events: list[str] = []
    harness.translator.close.side_effect = lambda: events.append("translator-closed")
    harness.audio.cleanup.side_effect = lambda: events.append("audio-cleaned")
    harness.worker.finished.connect(lambda _: events.append("finished"))

    harness.worker.run()

    assert events == ["translator-closed", "audio-cleaned", "finished"]


class ImmediateTerminalWorker(QObject):
    finished = pyqtSignal(dict)
    error = pyqtSignal(str)
    cancelled = pyqtSignal()
    progress = pyqtSignal(int, str, int)
    log = pyqtSignal(str, int)
    instances: list["ImmediateTerminalWorker"] = []

    def __init__(self, *args: Any, **kwargs: Any):
        super().__init__()
        del args
        self.config = kwargs or {}
        self.cancel_called = False
        self.instances.append(self)

    def run(self) -> None:
        self.finished.emit({"status": "completed"})

    def cancel(self) -> None:
        self.cancel_called = True


@pytest.mark.gui
def test_processing_widget_thread_exits_and_allows_next_task(
    qtbot, monkeypatch, tmp_path
):
    ImmediateTerminalWorker.instances.clear()
    monkeypatch.setattr(
        "app.gui.processing.ImprovedProcessingWorker", ImmediateTerminalWorker
    )
    config = {
        "whisper_model": "small",
        "translation_provider": "OpenAI",
        "api_keys": {"openai": "secret"},
    }
    widget = ProcessingWidget(config)
    qtbot.addWidget(widget)
    completed: list[dict[str, Any]] = []
    widget.processing_completed.connect(completed.append)

    widget.start_processing(str(tmp_path / "one.mp4"), "en", "zh-CN")
    qtbot.waitUntil(lambda: widget._thread is None, timeout=2_000)

    assert completed == [{"status": "completed"}]
    assert widget._worker is None
    assert not widget.is_processing

    widget.start_processing(str(tmp_path / "two.mp4"), "en", "ja")
    qtbot.waitUntil(lambda: widget._thread is None, timeout=2_000)
    assert len(completed) == 2
    assert len(ImmediateTerminalWorker.instances) == 2


@pytest.mark.gui
def test_processing_widget_cancel_requests_worker_without_terminating_thread(
    qtbot, monkeypatch, tmp_path
):
    class WaitingWorker(ImmediateTerminalWorker):
        def run(self) -> None:
            pass

        def cancel(self) -> None:
            super().cancel()
            self.cancelled.emit()

    monkeypatch.setattr("app.gui.processing.ImprovedProcessingWorker", WaitingWorker)
    widget = ProcessingWidget({})
    qtbot.addWidget(widget)
    cancelled: list[bool] = []
    widget.processing_cancelled.connect(lambda: cancelled.append(True))

    widget.start_processing(str(tmp_path / "movie.mp4"), "auto", "zh-CN")
    qtbot.waitUntil(lambda: widget._worker is not None, timeout=2_000)
    worker = widget._worker
    widget.cancel_processing()
    qtbot.waitUntil(lambda: widget._thread is None, timeout=2_000)

    assert worker.cancel_called
    assert cancelled == [True]
    assert widget.status_label.text() == "处理已取消，可稍后继续"
    assert not widget.is_processing
