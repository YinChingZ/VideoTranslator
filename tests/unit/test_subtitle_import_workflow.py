"""GUI contracts for subtitle import and the editor preview surface."""

from __future__ import annotations

from dataclasses import asdict

import pytest
from PyQt5.QtCore import Qt, QTimer
from PyQt5.QtGui import QPixmap
from PyQt5.QtWidgets import QMessageBox

from app.config import AppConfig
from app.core.subtitle import SubtitleProcessor, SubtitleSegment
from app.gui import main_window as main_window_module
from app.gui.main_window import MainWindow
from app.gui.subtitle_editor import SubtitleEditor
from app.utils.temp_files import TempFileManager

pytestmark = pytest.mark.gui


class _ConfigManagerStub:
    def __init__(self, config):
        self.config = config
        self.added = []

    def add_recent_file(self, path):
        self.added.append(path)
        self.config.recent_files.insert(0, path)
        return True


def _window(tmp_path, qtbot, monkeypatch):
    config = AppConfig()
    manager = _ConfigManagerStub(config)
    monkeypatch.setattr(main_window_module, "get_config_manager", lambda: manager)
    window = MainWindow(config, TempFileManager(base_dir=str(tmp_path / "temp")))
    qtbot.addWidget(window)
    window.subtitle_editor_widget.subtitle_timer.stop()
    monkeypatch.setattr(
        window.subtitle_editor_widget, "_prepare_video_playback", lambda *_args: None
    )
    monkeypatch.setattr(
        window.subtitle_editor_widget, "_apply_aspect_ratio", lambda: None
    )
    monkeypatch.setattr(window, "confirm_discard_changes", lambda: True)
    return window, manager


def _seed_editor(window):
    segment = SubtitleSegment(0.0, 1.0, "existing", "旧", 1)
    editor = window.subtitle_editor_widget
    editor.segments = [segment]
    editor._sync_processor_segments()
    editor.populate_segment_list()
    editor.clear_undo_history()


def test_import_subtitle_skips_processing_and_commits_complete_state(
    tmp_path, qtbot, monkeypatch
):
    window, manager = _window(tmp_path, qtbot, monkeypatch)
    video = tmp_path / "movie.mp4"
    video.touch()
    subtitle = tmp_path / "captions.srt"
    subtitle.write_text(
        "1\n00:00:00,000 --> 00:00:01,500\nHello\n\n"
        "2\n00:00:02,000 --> 00:00:03,000\nWorld\n",
        encoding="utf-8",
    )

    assert window.import_subtitle_file(str(subtitle), video_filepath=str(video))

    editor = window.subtitle_editor_widget
    assert window.stacked_widget.currentIndex() == 2
    assert window.current_video_path == str(video)
    assert window.current_file_path == str(video)
    assert window.current_project_path is None
    assert window.current_subtitle_path == str(subtitle)
    assert window.workflow.get_data("video_path") == str(video)
    assert window.workflow.get_data("processing_results")["is_subtitle_import"]
    assert [segment.original_text for segment in editor.segments] == ["Hello", "World"]
    assert editor.subtitle_processor.segments is editor.segments
    assert editor.undo_stack.count() == 0
    assert window.has_unsaved_changes
    assert window.windowTitle().endswith(" *")
    assert manager.added == [str(subtitle)]
    assert window.config["last_directory"] == str(tmp_path)


def test_parse_failure_does_not_replace_existing_session(
    tmp_path, qtbot, monkeypatch
):
    window, manager = _window(tmp_path, qtbot, monkeypatch)
    video = tmp_path / "movie.mp4"
    video.touch()
    broken = tmp_path / "broken.sbv"
    broken.write_text("not a valid subtitle", encoding="utf-8")
    _seed_editor(window)
    before = [asdict(segment) for segment in window.subtitle_editor_widget.segments]
    warnings = []
    monkeypatch.setattr(
        QMessageBox,
        "warning",
        lambda *args: warnings.append(args[2]),
    )

    assert not window.import_subtitle_file(str(broken), video_filepath=str(video))
    assert [asdict(segment) for segment in window.subtitle_editor_widget.segments] == before
    assert window.current_video_path is None
    assert window.current_subtitle_path is None
    assert not window.has_unsaved_changes
    assert manager.added == []
    assert warnings and "无法解析" in warnings[0]


def test_cancel_and_replacement_confirmation_are_non_destructive(
    tmp_path, qtbot, monkeypatch
):
    window, _manager = _window(tmp_path, qtbot, monkeypatch)
    video = tmp_path / "movie.mp4"
    video.touch()
    subtitle = tmp_path / "captions.vtt"
    subtitle.write_text(
        "WEBVTT\n\n00:00:00.000 --> 00:00:01.000\nReplacement\n",
        encoding="utf-8",
    )
    _seed_editor(window)
    window._set_unsaved_changes(True)
    before = [asdict(segment) for segment in window.subtitle_editor_widget.segments]
    monkeypatch.setattr(window, "confirm_discard_changes", lambda: False)

    assert not window.import_subtitle_file(str(subtitle), video_filepath=str(video))
    assert [asdict(segment) for segment in window.subtitle_editor_widget.segments] == before

    window._set_unsaved_changes(False)
    monkeypatch.setattr(
        main_window_module.QFileDialog,
        "getOpenFileName",
        lambda *_args, **_kwargs: ("", ""),
    )
    assert not window.import_subtitle_file()
    assert [asdict(segment) for segment in window.subtitle_editor_widget.segments] == before


def test_missing_video_uses_injectable_picker_and_can_cancel(
    tmp_path, qtbot, monkeypatch
):
    window, _manager = _window(tmp_path, qtbot, monkeypatch)
    subtitle = tmp_path / "captions.ass"
    subtitle.write_text(
        "[Events]\n"
        "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, "
        "Effect, Text\n"
        "Dialogue: 0,0:00:00.00,0:00:01.00,Default,,0,0,0,,Hello\n",
        encoding="utf-8",
    )
    picked_from = []
    monkeypatch.setattr(
        window,
        "_choose_video_for_subtitle_import",
        lambda directory: picked_from.append(directory) or "",
    )

    assert not window.import_subtitle_file(str(subtitle))
    assert picked_from == [str(tmp_path)]
    assert window.current_video_path is None
    assert window.subtitle_editor_widget.segments == []


@pytest.mark.parametrize("suffix", ["srt", "vtt", "ass", "ssa", "sub", "sbv"])
def test_import_dialog_advertises_every_core_readable_format(suffix):
    assert f"*.{suffix}" in MainWindow._subtitle_file_filter()


def test_menu_action_uses_dialog_instead_of_passing_qaction_checked_flag(
    tmp_path, qtbot, monkeypatch
):
    window, _manager = _window(tmp_path, qtbot, monkeypatch)
    received = []
    monkeypatch.setattr(
        window,
        "import_subtitle_file",
        lambda filepath=None, **_kwargs: received.append(filepath),
    )

    window.import_subtitle_action.trigger()
    assert received == [None]


def test_import_can_use_video_already_selected_on_import_page(
    tmp_path, qtbot, monkeypatch
):
    window, _manager = _window(tmp_path, qtbot, monkeypatch)
    video = tmp_path / "selected.mp4"
    video.touch()
    subtitle = tmp_path / "captions.sbv"
    subtitle.write_text(
        "0:00:00.000,0:00:01.000\nAlready selected\n", encoding="utf-8"
    )
    window.video_import_widget.video_path = str(video)
    window.video_import_widget.video_info = {"duration": 42.0, "width": 1920, "height": 1080}
    window.workflow.set_data("video_path", str(video))
    window.workflow.set_data("video_info", dict(window.video_import_widget.video_info))
    monkeypatch.setattr(
        window,
        "_choose_video_for_subtitle_import",
        lambda _directory: pytest.fail("video picker should not open"),
    )

    assert window.import_subtitle_file(str(subtitle))
    assert window.current_video_path == str(video)
    assert window.subtitle_editor_widget.segments[0].original_text == "Already selected"
    assert window.workflow.get_data("video_info")["duration"] == 42.0
    assert window.subtitle_editor_widget.timeline.duration == pytest.approx(42.0)


def test_subtitle_is_video_overlay_and_resize_never_fixes_preview_height(
    qtbot, monkeypatch
):
    processor = SubtitleProcessor()
    processor.segments = [SubtitleSegment(0.0, 2.0, "Hello", "你好", 1)]
    editor = SubtitleEditor("", processor)
    qtbot.addWidget(editor)
    editor.subtitle_timer.stop()
    editor.resize(720, 520)
    editor.show()
    qtbot.wait(10)

    assert editor.subtitle_overlay_layer.parent() is editor.video_stack
    assert editor.subtitle_overlay_layer.testAttribute(Qt.WA_TransparentForMouseEvents)
    assert editor.subtitle_display.testAttribute(Qt.WA_TransparentForMouseEvents)
    editor.current_position = 1.0
    editor.update_subtitle_display()
    assert editor.subtitle_display.isVisible()
    assert editor.subtitle_display.text() == "Hello\n\n你好"

    editor._apply_aspect_ratio()
    assert editor.video_widget.maximumHeight() == 16_777_215
    assert editor.fallback_image_label.maximumHeight() == 16_777_215

    source = QPixmap(320, 180)
    source.fill(Qt.GlobalColor.red)
    editor._fallback_source_pixmap = source
    editor._scale_fallback_pixmap()
    assert not editor.fallback_image_label.pixmap().isNull()


def test_fallback_generation_discards_stale_result(qtbot):
    processor = SubtitleProcessor()
    editor = SubtitleEditor("first.mp4", processor)
    qtbot.addWidget(editor)
    editor.subtitle_timer.stop()
    editor._fallback_generation = 4
    editor.video_path = "second.mp4"
    frame = QPixmap(16, 9)
    frame.fill(Qt.GlobalColor.blue)
    from PyQt5.QtCore import QBuffer, QIODevice

    buffer = QBuffer()
    buffer.open(QIODevice.OpenModeFlag.WriteOnly)
    assert frame.save(buffer, "PNG")
    png_data = bytes(buffer.data())

    editor._fallback_frame_ready(3, "first.mp4", png_data)
    assert editor._fallback_source_pixmap.isNull()
    editor._fallback_frame_ready(4, "second.mp4", png_data)
    assert not editor._fallback_source_pixmap.isNull()


def test_media_fallback_returns_before_worker_completes(qtbot, tmp_path, monkeypatch):
    video = tmp_path / "movie.mp4"
    video.touch()
    editor = SubtitleEditor(str(video), SubtitleProcessor())
    qtbot.addWidget(editor)
    editor.subtitle_timer.stop()
    started = []
    monkeypatch.setattr("app.gui.subtitle_editor.shutil.which", lambda _name: "/ffmpeg")
    monkeypatch.setattr(
        editor._fallback_thread_pool,
        "start",
        lambda task: started.append(task),
    )
    heartbeat = []
    QTimer.singleShot(0, lambda: heartbeat.append(True))

    editor._media_fallback()
    qtbot.waitUntil(lambda: bool(heartbeat), timeout=500)
    assert len(started) == 1
    assert editor.fallback_image_label.text() == "正在生成静态预览…"


def test_closing_editor_cancels_object_owned_playback_timers(qtbot, monkeypatch):
    editor = SubtitleEditor("", SubtitleProcessor())
    qtbot.addWidget(editor)
    editor.subtitle_timer.stop()
    calls = []
    monkeypatch.setattr(
        editor, "_prepare_video_playback", lambda *_args: calls.append("prepare")
    )
    monkeypatch.setattr(editor, "_init_vlc_playback", lambda *_args: calls.append("vlc"))

    editor._scheduled_project_import = True
    editor._playback_prepare_timer.start(10)
    editor._vlc_init_timer.start(10)
    editor.shutdown_media_preview()
    qtbot.wait(30)

    assert calls == []
    assert not editor._playback_prepare_timer.isActive()
    assert not editor._vlc_init_timer.isActive()
