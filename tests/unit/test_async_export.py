"""Production regressions for the non-blocking export pipeline."""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PyQt5")

from PyQt5.QtCore import QEventLoop, QThread, QTimer
from PyQt5.QtWidgets import QApplication, QMessageBox

from app.config import AppConfig
from app.core.subtitle import SubtitleProcessor
from app.core.video import VideoProcessor
from app.gui.main_window import MainWindow
from app.gui.video_export_thread import VideoExportWorker
from app.utils.temp_files import TempFileManager


@pytest.fixture(scope="module")
def qapp():
    return QApplication.instance() or QApplication([])


def _segments():
    return [
        {
            "start_time": 0.0,
            "end_time": 1.5,
            "original_text": "Hello",
            "translated_text": "你好",
            "index": 1,
        }
    ]


def _subtitle_options(tmp_path: Path, **overrides):
    options = {
        "output_dir": str(tmp_path),
        "filename": "translated",
        "format": "srt",
        "language_option": "bilingual",
        "embed_subtitles": False,
        "hardcode_subtitles": False,
        "overwrite_existing": False,
        "subtitle_data": _segments(),
    }
    options.update(overrides)
    return options


def _run_worker_thread(worker: VideoExportWorker, qapp, cancel_after_ms=None):
    outcomes = {"succeeded": [], "failed": [], "cancelled": 0, "finished": 0}
    worker.succeeded.connect(
        lambda output, message: outcomes["succeeded"].append((output, message))
    )
    worker.failed.connect(lambda message: outcomes["failed"].append(message))
    worker.cancelled.connect(
        lambda: outcomes.__setitem__("cancelled", outcomes["cancelled"] + 1)
    )
    worker.finished.connect(
        lambda: outcomes.__setitem__("finished", outcomes["finished"] + 1)
    )

    thread = QThread()
    worker.moveToThread(thread)
    thread.started.connect(worker.run)
    worker.finished.connect(thread.quit)

    loop = QEventLoop()
    thread.finished.connect(loop.quit)
    if cancel_after_ms is not None:
        # Wrap the call so Qt does not queue the bound QObject method onto the
        # busy worker event loop; cancel() is explicitly thread-safe.
        QTimer.singleShot(cancel_after_ms, lambda: worker.cancel())

    timeout = QTimer()
    timeout.setSingleShot(True)
    timeout.timeout.connect(lambda: worker.cancel())
    timeout.start(5000)
    thread.start()
    loop.exec()
    timeout.stop()
    assert thread.wait(1000)
    return outcomes


def test_subtitle_export_preserves_language_mode_and_has_distinct_success(tmp_path):
    worker = VideoExportWorker(_subtitle_options(tmp_path))
    outcomes = {"success": [], "error": [], "cancel": 0, "finished": 0}
    worker.succeeded.connect(
        lambda path, message: outcomes["success"].append((path, message))
    )
    worker.failed.connect(lambda message: outcomes["error"].append(message))
    worker.cancelled.connect(
        lambda: outcomes.__setitem__("cancel", outcomes["cancel"] + 1)
    )
    worker.finished.connect(
        lambda: outcomes.__setitem__("finished", outcomes["finished"] + 1)
    )

    worker.run()

    assert len(outcomes["success"]) == 1
    assert outcomes["error"] == []
    assert outcomes["cancel"] == 0
    assert outcomes["finished"] == 1
    output = Path(outcomes["success"][0][0])
    assert output.read_text(encoding="utf-8").endswith("Hello\n你好\n")


def test_existing_destination_is_not_replaced_without_confirmation(tmp_path):
    destination = tmp_path / "translated.srt"
    destination.write_text("keep me", encoding="utf-8")
    worker = VideoExportWorker(_subtitle_options(tmp_path))
    failures = []
    successes = []
    worker.failed.connect(failures.append)
    worker.succeeded.connect(lambda *args: successes.append(args))

    worker.run()

    assert successes == []
    assert len(failures) == 1
    assert "未覆盖" in failures[0]
    assert destination.read_text(encoding="utf-8") == "keep me"
    assert list(tmp_path.glob(".videotranslator-export-*")) == []


def test_video_export_cancellation_stops_child_and_preserves_destination(
    tmp_path, qapp, monkeypatch
):
    source = tmp_path / "source.mp4"
    source.write_bytes(b"source")
    destination = tmp_path / "translated.mp4"
    destination.write_bytes(b"existing destination")
    options = _subtitle_options(
        tmp_path,
        video_path=str(source),
        video_format="mp4",
        hardcode_subtitles=True,
        overwrite_existing=True,
    )
    worker = VideoExportWorker(options)

    def slow_child(_video_path, _subtitle_path, output_path, _video_format):
        script = (
            "from pathlib import Path; import sys, time; "
            "Path(sys.argv[1]).write_bytes(b'partial'); time.sleep(30)"
        )
        return [sys.executable, "-c", script, str(output_path)]

    monkeypatch.setattr(worker, "_hardcode_command", slow_child)
    monkeypatch.setattr(
        VideoProcessor,
        "check_subtitle_filter_available",
        classmethod(lambda cls, ffmpeg_path="ffmpeg", filter_name="subtitles": True),
    )
    outcomes = _run_worker_thread(worker, qapp, cancel_after_ms=150)

    assert outcomes["cancelled"] == 1
    assert outcomes["succeeded"] == []
    assert outcomes["failed"] == []
    assert outcomes["finished"] == 1
    assert destination.read_bytes() == b"existing destination"
    assert list(tmp_path.glob(".videotranslator-export-*")) == []


def test_video_export_rejects_non_media_output_and_preserves_destination(
    tmp_path, monkeypatch
):
    source = tmp_path / "source.mp4"
    source.write_bytes(b"source")
    destination = tmp_path / "translated.mp4"
    destination.write_bytes(b"keep-existing")
    worker = VideoExportWorker(
        _subtitle_options(
            tmp_path,
            video_path=str(source),
            video_format="mp4",
            embed_subtitles=True,
            overwrite_existing=True,
        )
    )

    def fake_success(command, cwd):
        del cwd
        Path(command[-1]).write_bytes(b"not a media container")

    monkeypatch.setattr(worker, "_run_ffmpeg", fake_success)
    failures = []
    successes = []
    worker.failed.connect(failures.append)
    worker.succeeded.connect(lambda *args: successes.append(args))

    worker.run()

    assert successes == []
    assert len(failures) == 1
    assert destination.read_bytes() == b"keep-existing"
    assert list(tmp_path.glob(".videotranslator-export-*")) == []


@pytest.mark.skipif(shutil.which("ffmpeg") is None, reason="FFmpeg is unavailable")
def test_real_ffmpeg_soft_subtitle_export(tmp_path, qapp):
    source = tmp_path / "source.mp4"
    subprocess.run(
        [
            "ffmpeg",
            "-hide_banner",
            "-loglevel",
            "error",
            "-f",
            "lavfi",
            "-i",
            "color=c=black:s=160x90:d=0.3",
            "-c:v",
            "libx264",
            "-pix_fmt",
            "yuv420p",
            "-y",
            str(source),
        ],
        check=True,
    )
    worker = VideoExportWorker(
        _subtitle_options(
            tmp_path,
            filename="with-subtitles",
            video_path=str(source),
            video_format="mp4",
            embed_subtitles=True,
            target_language="zh-CN",
        )
    )

    outcomes = _run_worker_thread(worker, qapp)

    assert len(outcomes["succeeded"]) == 1
    assert outcomes["failed"] == []
    output = Path(outcomes["succeeded"][0][0])
    assert output.is_file() and output.stat().st_size > 0
    probe = subprocess.run(
        [
            "ffprobe",
            "-v",
            "error",
            "-select_streams",
            "s:0",
            "-show_entries",
            "stream=codec_name:stream_tags=language",
            "-of",
            "default=noprint_wrappers=1",
            str(output),
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    assert "codec_name=mov_text" in probe.stdout
    assert "TAG:language=zho" in probe.stdout


def test_main_window_keeps_event_loop_responsive_and_rejects_duplicate_export(
    tmp_path, qapp, monkeypatch
):
    original_save = SubtitleProcessor.save_to_file

    def deliberately_slow_save(processor, *args, **kwargs):
        time.sleep(0.25)
        return original_save(processor, *args, **kwargs)

    monkeypatch.setattr(SubtitleProcessor, "save_to_file", deliberately_slow_save)
    window = MainWindow(AppConfig(), TempFileManager(base_dir=str(tmp_path / "temp")))
    window.stacked_widget.setCurrentIndex(2)
    window.update_action_states(2)

    ticks = []
    heartbeat = QTimer()
    heartbeat.setInterval(10)
    heartbeat.timeout.connect(lambda: ticks.append(time.monotonic()))
    heartbeat.start()
    try:
        assert window._start_export(_subtitle_options(tmp_path)) is True
        active_thread = window._export_thread
        assert active_thread is not None
        assert window._start_export(_subtitle_options(tmp_path)) is False
        assert not window.export_action.isEnabled()

        loop = QEventLoop()
        active_thread.finished.connect(loop.quit)
        timeout = QTimer()
        timeout.setSingleShot(True)
        timeout.timeout.connect(window.cancel_export)
        timeout.start(5000)
        loop.exec()
        timeout.stop()
        qapp.processEvents()

        assert len(ticks) >= 5
        assert window._export_thread is None
        assert window._export_worker is None
        assert window.export_action.isEnabled()
        assert (tmp_path / "translated.srt").is_file()
    finally:
        heartbeat.stop()
        if window.is_exporting:
            window.cancel_export()
            window._export_thread.wait(3000)
        window.close()


def test_closing_window_cooperatively_cancels_export(
    tmp_path, qapp, monkeypatch
):
    original_save = SubtitleProcessor.save_to_file

    def deliberately_slow_save(processor, *args, **kwargs):
        time.sleep(0.2)
        return original_save(processor, *args, **kwargs)

    monkeypatch.setattr(SubtitleProcessor, "save_to_file", deliberately_slow_save)
    monkeypatch.setattr(
        QMessageBox,
        "question",
        staticmethod(lambda *args, **kwargs: QMessageBox.StandardButton.Yes),
    )
    window = MainWindow(AppConfig(), TempFileManager(base_dir=str(tmp_path / "temp")))
    window.stacked_widget.setCurrentIndex(2)
    window.show()
    assert window._start_export(_subtitle_options(tmp_path)) is True
    active_thread = window._export_thread
    assert active_thread is not None

    loop = QEventLoop()
    active_thread.finished.connect(loop.quit)
    QTimer.singleShot(30, window.close)
    timeout = QTimer()
    timeout.setSingleShot(True)
    timeout.timeout.connect(lambda: window.cancel_export())
    timeout.start(5000)
    loop.exec()
    timeout.stop()
    qapp.processEvents()

    assert window._export_thread is None
    assert window._export_worker is None
    assert not window.isVisible()
    assert not (tmp_path / "translated.srt").exists()
    assert list(tmp_path.glob(".videotranslator-export-*")) == []
