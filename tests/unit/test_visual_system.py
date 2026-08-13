"""Offscreen regression tests for themes, icons, and video import access."""

from __future__ import annotations

import os
import threading
import time
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PyQt5")

from PyQt5.QtCore import QBuffer, QByteArray, QIODevice, QMimeData, QPoint, Qt, QUrl
from PyQt5.QtGui import QColor, QDragEnterEvent, QImage
from PyQt5.QtTest import QSignalSpy, QTest
from PyQt5.QtWidgets import QApplication, QWidget

from app.gui.video_import import DropZone, VideoImportWidget, _VideoLoadResult
from app.resources.icons import IconManager
from app.resources.styles import DARK_THEME, LIGHT_THEME, StyleManager


@pytest.fixture(scope="module")
def qapp():
    return QApplication.instance() or QApplication([])


def _contrast_ratio(first: str, second: str) -> float:
    def luminance(hex_color: str) -> float:
        channels = [int(hex_color[index : index + 2], 16) / 255 for index in (1, 3, 5)]
        linear = [value / 12.92 if value <= 0.04045 else ((value + 0.055) / 1.055) ** 2.4 for value in channels]
        return 0.2126 * linear[0] + 0.7152 * linear[1] + 0.0722 * linear[2]

    lighter, darker = sorted((luminance(first), luminance(second)), reverse=True)
    return (lighter + 0.05) / (darker + 0.05)


def test_styles_use_native_fonts_and_embedded_qss_only(qapp):
    manager = StyleManager()
    light_qss = manager._generate_stylesheet(LIGHT_THEME)
    dark_qss = manager._generate_stylesheet(DARK_THEME)

    for stylesheet in (light_qss, dark_qss):
        assert "font-family" not in stylesheet
        assert "url(" not in stylesheet
        assert '#dropZone:focus' in stylesheet
        assert '#dropZone[dragActive="true"]' in stylesheet
        assert 'QPushButton[primary="true"]:disabled' in stylesheet

    for theme in (LIGHT_THEME, DARK_THEME):
        assert _contrast_ratio(theme["text"], theme["background"]) >= 7
        assert _contrast_ratio(theme["text"], theme["surface"]) >= 7
        assert _contrast_ratio(theme["text_on_primary"], theme["primary"]) >= 4.5
        assert _contrast_ratio(theme["disabled_text"], theme["disabled_surface"]) >= 3

    target = QWidget()
    try:
        assert manager.apply_theme("dark", target) == "dark"
        assert manager.current_theme == "dark"
        assert target.styleSheet() == dark_qss

        assert manager.apply_theme("light", target) == "light"
        assert manager.current_theme == "light"
        assert target.palette().window().color().name().upper() == LIGHT_THEME["background"]
    finally:
        target.close()


def test_missing_icons_have_deterministic_theme_aware_vector_fallbacks(qapp, tmp_path):
    manager = IconManager(str(tmp_path))

    light_icon = manager.get_icon("open")
    repeated_icon = manager.get_icon("open")
    unknown_icon = manager.get_icon("not-an-action")
    assert not light_icon.isNull()
    assert light_icon.cacheKey() == repeated_icon.cacheKey()
    assert not unknown_icon.isNull()
    assert not unknown_icon.pixmap(24, 24).isNull()

    manager.set_theme("dark")
    dark_icon = manager.get_icon("open")
    assert not dark_icon.isNull()
    assert dark_icon.cacheKey() != light_icon.cacheKey()
    assert ("dark", "open") in manager.icon_cache
    assert ("light", "open") not in manager.icon_cache


def test_drop_zone_is_keyboard_accessible_and_validates_dragged_files(qapp, tmp_path):
    zone = DropZone(supported_extensions=["mp4"])
    zone.show()
    try:
        assert zone.focusPolicy() == Qt.StrongFocus
        assert zone.accessibleName() == "视频文件导入区域"
        assert "Enter" in zone.accessibleDescription()

        browse_spy = QSignalSpy(zone.browse_requested)
        QTest.keyClick(zone, Qt.Key_Return)
        QTest.keyClick(zone, Qt.Key_Space)
        assert len(browse_spy) == 2

        video_file = tmp_path / "sample.mp4"
        video_file.write_bytes(b"placeholder")
        valid_mime = QMimeData()
        valid_mime.setUrls([QUrl.fromLocalFile(str(video_file))])
        valid_event = QDragEnterEvent(
            QPoint(5, 5),
            Qt.CopyAction,
            valid_mime,
            Qt.LeftButton,
            Qt.NoModifier,
        )
        QApplication.sendEvent(zone, valid_event)
        assert valid_event.isAccepted()
        assert zone.property("dragActive") is True

        text_file = tmp_path / "sample.txt"
        text_file.write_text("not video", encoding="utf-8")
        invalid_mime = QMimeData()
        invalid_mime.setUrls([QUrl.fromLocalFile(str(text_file))])
        invalid_event = QDragEnterEvent(
            QPoint(5, 5),
            Qt.CopyAction,
            invalid_mime,
            Qt.LeftButton,
            Qt.NoModifier,
        )
        QApplication.sendEvent(zone, invalid_event)
        assert not invalid_event.isAccepted()
        assert zone.property("dragActive") is False
    finally:
        zone.close()


def test_video_import_exposes_labels_and_primary_action(qapp):
    widget = VideoImportWidget(
        {
            "language_codes": {"en": "English", "zh-CN": "简体中文"},
            "default_target_language": "zh-CN",
            "supported_video_formats": ["mp4", "mkv"],
            "theme": "dark",
        }
    )
    try:
        assert widget.objectName() == "videoImportWidget"
        assert widget.source_lang_combo.accessibleName() == "源语言"
        assert widget.target_lang_combo.accessibleName() == "目标语言"
        assert widget.continue_btn.property("primary") is True
        assert widget.drop_zone.supported_extensions == frozenset({".mp4", ".mkv"})
        assert widget.icon_manager.current_theme == "dark"
    finally:
        widget.close()


def _jpeg_bytes() -> bytes:
    image = QImage(32, 18, QImage.Format_RGB32)
    image.fill(QColor("#2563EB"))
    data = QByteArray()
    buffer = QBuffer(data)
    assert buffer.open(QIODevice.WriteOnly)
    assert image.save(buffer, "JPG")
    return bytes(data)


def test_video_import_probe_and_thumbnail_run_off_the_gui_thread(qapp, tmp_path):
    class FakeProcessor:
        def __init__(self):
            self.probe_thread = None
            self.thumbnail_thread = None

        def get_video_info(self, video_path):
            self.probe_thread = threading.current_thread()
            return {"filename": Path(video_path).name, "duration": 65, "width": 1280, "height": 720}

        def generate_thumbnail(self, video_path, time_pos, width):
            self.thumbnail_thread = threading.current_thread()
            thumbnail = tmp_path / "preview.jpg"
            thumbnail.write_bytes(_jpeg_bytes())
            return str(thumbnail)

    video_file = tmp_path / "video.mp4"
    video_file.write_bytes(b"media")
    widget = VideoImportWidget({"supported_video_formats": ["mp4"]})
    processor = FakeProcessor()
    widget.video_processor = processor
    loaded_spy = QSignalSpy(widget.video_info_loaded)
    try:
        widget.set_video_path(str(video_file))
        assert not widget.continue_btn.isEnabled()
        assert loaded_spy.wait(2_000)
        assert processor.probe_thread is not threading.current_thread()
        assert processor.thumbnail_thread is processor.probe_thread
        assert widget.duration_label.text() == "00:01:05"
        assert widget.resolution_label.text() == "1280 × 720"
        assert widget.continue_btn.isEnabled()
        assert not widget.thumbnail_label.pixmap().isNull()
        assert widget.video_info == loaded_spy[0][0]
        assert not (tmp_path / "preview.jpg").exists()
    finally:
        widget.close()


def test_video_import_ignores_stale_results_after_fast_switch(qapp, tmp_path):
    class SwitchingProcessor:
        def get_video_info(self, video_path):
            if video_path.endswith("first.mp4"):
                time.sleep(0.12)
                return {"filename": "first.mp4", "duration": 1, "width": 100, "height": 100}
            return {"filename": "second.mp4", "duration": 2, "width": 200, "height": 100}

        def generate_thumbnail(self, video_path, time_pos, width):
            return None

    first = tmp_path / "first.mp4"
    second = tmp_path / "second.mp4"
    first.write_bytes(b"first")
    second.write_bytes(b"second")
    widget = VideoImportWidget({"supported_video_formats": ["mp4"]})
    widget.video_processor = SwitchingProcessor()
    loaded_spy = QSignalSpy(widget.video_info_loaded)
    try:
        widget.set_video_path(str(first))
        widget.set_video_path(str(second))
        assert loaded_spy.wait(2_000)
        deadline = time.monotonic() + 1
        while widget._active_load_tasks and time.monotonic() < deadline:
            qapp.processEvents()
            time.sleep(0.01)
        assert len(loaded_spy) == 1
        assert loaded_spy[0][0]["filename"] == "second.mp4"
        assert widget.filename_label.text() == "second.mp4"
        assert widget.resolution_label.text() == "200 × 100"
    finally:
        widget.close()


def test_video_import_failure_is_reported_and_disables_continue(qapp, tmp_path):
    class FailingProcessor:
        def get_video_info(self, video_path):
            return {"error": "invalid media"}

    video_file = tmp_path / "broken.mp4"
    video_file.write_bytes(b"broken")
    widget = VideoImportWidget({"supported_video_formats": ["mp4"]})
    widget.video_processor = FailingProcessor()
    error_spy = QSignalSpy(widget.video_info_error)
    try:
        widget.set_video_path(str(video_file))
        assert error_spy.wait(2_000)
        assert error_spy[0][0] == "invalid media"
        assert not widget.continue_btn.isEnabled()
        assert widget.duration_label.text() == "未知"
    finally:
        widget.close()


def test_stale_result_after_close_does_not_update_widget(qapp):
    widget = VideoImportWidget({"supported_video_formats": ["mp4"]})
    widget.video_path = "/tmp/current.mp4"
    widget._load_generation = 4
    widget.close()
    result = _VideoLoadResult(
        request_id=4,
        video_path="/tmp/current.mp4",
        info={"filename": "should-not-appear.mp4", "duration": 9},
        thumbnail_data=b"",
    )
    widget._video_load_finished(result)
    assert widget.filename_label.text() != "should-not-appear.mp4"
