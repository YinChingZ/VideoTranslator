"""Contracts between the export dialog, worker, and subtitle serializers."""

from __future__ import annotations

import pytest

pytest.importorskip("PyQt5")

from PyQt5.QtGui import QIcon
from PyQt5.QtWidgets import QApplication, QWidget

from app.gui.export_dialog import ExportDialog
from app.gui.video_export_thread import VideoExportWorker


@pytest.fixture(scope="module")
def qapp():
    return QApplication.instance() or QApplication([])


def _dialog(tmp_path):
    class IconStub:
        @staticmethod
        def get_icon(_name):
            return QIcon()

    parent = QWidget()
    parent.icon_manager = IconStub()
    dialog = ExportDialog(
        parent,
        {"output_dir": str(tmp_path), "language_codes": {}},
        str(tmp_path / "video.mp4"),
    )
    # Keep the Qt parent alive for the dialog's lifetime.
    dialog._test_parent = parent
    return dialog


def test_dialog_exposes_every_standalone_text_format(qapp, tmp_path):
    dialog = _dialog(tmp_path)
    try:
        formats = {
            dialog.format_combo.itemData(index)
            for index in range(dialog.format_combo.count())
        }
        video_formats = {
            dialog.video_format_combo.itemData(index)
            for index in range(dialog.video_format_combo.count())
        }

        assert {"srt", "vtt", "ass", "ssa", "sbv", "sub"} <= formats
        assert {"mp4", "mkv", "mov", "webm", "same"} <= video_formats
        assert not hasattr(dialog, "progress_bar")
    finally:
        dialog.close()


@pytest.mark.parametrize("subtitle_format", ["sbv", "sub"])
def test_legacy_text_formats_disable_video_options(
    qapp, tmp_path, subtitle_format
):
    dialog = _dialog(tmp_path)
    try:
        index = dialog.format_combo.findData(subtitle_format)
        dialog.format_combo.setCurrentIndex(index)

        assert not dialog.embed_checkbox.isEnabled()
        assert not dialog.hardcode_checkbox.isEnabled()
        assert "仅用于导出字幕文件" in dialog.embed_checkbox.toolTip()
    finally:
        dialog.close()


@pytest.mark.parametrize("subtitle_format", ["sbv", "sub"])
def test_worker_exports_all_declared_standalone_formats(
    tmp_path, subtitle_format
):
    worker = VideoExportWorker(
        {
            "output_dir": str(tmp_path),
            "filename": f"captions-{subtitle_format}",
            "format": subtitle_format,
            "language_option": "bilingual",
            "subtitle_data": [
                {
                    "start_time": 0.0,
                    "end_time": 1.0,
                    "original_text": "Hello",
                    "translated_text": "你好",
                }
            ],
        }
    )
    succeeded = []
    failed = []
    worker.succeeded.connect(lambda path, _message: succeeded.append(path))
    worker.failed.connect(failed.append)

    worker.run()

    assert failed == []
    assert len(succeeded) == 1
    content = (tmp_path / f"captions-{subtitle_format}.{subtitle_format}").read_text(
        encoding="utf-8"
    )
    assert "Hello" in content and "你好" in content


def test_worker_rejects_sbv_video_embedding_before_ffmpeg(tmp_path):
    worker = VideoExportWorker(
        {
            "output_dir": str(tmp_path),
            "filename": "captions",
            "format": "sbv",
            "language_option": "bilingual",
            "embed_subtitles": True,
            "subtitle_data": [
                {
                    "start_time": 0.0,
                    "end_time": 1.0,
                    "original_text": "Hello",
                    "translated_text": "你好",
                }
            ],
        }
    )
    failed = []
    worker.failed.connect(failed.append)

    worker.run()

    assert len(failed) == 1
    assert "仅支持字幕文件导出" in failed[0]
