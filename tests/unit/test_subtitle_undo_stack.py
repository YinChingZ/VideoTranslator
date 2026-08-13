"""Production contract for editor-wide subtitle undo and redo."""

from __future__ import annotations

import json
from dataclasses import asdict

import pytest
from PyQt5.QtGui import QTextCursor
from PyQt5.QtTest import QTest

from app.config import AppConfig
from app.core.subtitle import SubtitleProcessor, SubtitleSegment
from app.gui import main_window as main_window_module
from app.gui.main_window import MainWindow
from app.gui.subtitle_editor import SubtitleEditor, SubtitleListItem
from app.utils.temp_files import TempFileManager

pytestmark = pytest.mark.gui


def _segments():
    return [
        SubtitleSegment(0.0, 1.5, "One", "一", 1, {"fontsize": "24"}),
        SubtitleSegment(1.5, 3.0, "Two", "二", 2),
        SubtitleSegment(3.0, 4.5, "Three", "三", 3),
    ]


def _editor(qtbot):
    processor = SubtitleProcessor()
    processor.segments = _segments()
    editor = SubtitleEditor("", processor)
    qtbot.addWidget(editor)
    editor.subtitle_timer.stop()
    editor.segment_list.setCurrentRow(0)
    return editor


def _state(editor):
    return [asdict(segment) for segment in editor.segments]


def _assert_views_are_synchronized(editor, selected_row):
    assert editor.subtitle_processor.segments is editor.segments
    assert editor.timeline.segments is editor.segments
    assert editor.segment_list.count() == len(editor.segments)
    assert editor.segment_list.currentRow() == selected_row
    assert editor.current_segment_index == selected_row
    for row, segment in enumerate(editor.segments):
        item = editor.segment_list.item(row)
        assert isinstance(item, SubtitleListItem)
        assert item.segment is segment
        assert segment.index == row + 1
    if selected_row >= 0:
        segment = editor.segments[selected_row]
        assert editor.original_text_edit.toPlainText() == segment.original_text
        assert editor.translation_text_edit.toPlainText() == segment.translated_text
        assert editor.start_time_edit.value() == pytest.approx(segment.start_time)
        assert editor.end_time_edit.value() == pytest.approx(segment.end_time)
        assert editor.timeline.selected_segment == selected_row


def test_text_and_timing_edits_share_one_model_history(qtbot):
    editor = _editor(qtbot)
    baseline = _state(editor)

    editor.original_text_edit.setFocus()
    editor.original_text_edit.moveCursor(QTextCursor.MoveOperation.End)
    QTest.keyClicks(editor.original_text_edit, " alpha")
    QTest.keyClicks(editor.original_text_edit, " beta")
    assert editor.undo_stack.count() == 1
    original_state = _state(editor)

    editor.translation_text_edit.setFocus()
    editor.translation_text_edit.moveCursor(QTextCursor.MoveOperation.End)
    QTest.keyClicks(editor.translation_text_edit, " translated")
    assert editor.undo_stack.count() == 2
    translated_state = _state(editor)

    editor.start_time_edit.setFocus()
    editor.start_time_edit.setValue(0.25)
    editor.end_time_edit.setValue(1.75)
    assert editor.undo_stack.count() == 3
    final_state = _state(editor)
    assert final_state[0]["original_text"].endswith(" alpha beta")
    assert final_state[0]["translated_text"].endswith(" translated")

    editor.undo()
    assert _state(editor) == translated_state
    _assert_views_are_synchronized(editor, 0)
    editor.undo()
    assert _state(editor) == original_state
    _assert_views_are_synchronized(editor, 0)
    editor.undo()
    assert _state(editor) == baseline
    _assert_views_are_synchronized(editor, 0)
    assert not editor.undo_stack.canUndo()
    assert editor.undo_stack.canRedo()

    editor.redo()
    editor.redo()
    editor.redo()
    assert _state(editor) == final_state
    _assert_views_are_synchronized(editor, 0)


def test_add_remove_merge_and_split_restore_all_views(qtbot):
    editor = _editor(qtbot)
    baseline = _state(editor)

    editor.current_position = 6.0
    editor.add_segment()
    added_state = _state(editor)
    assert len(added_state) == 4
    _assert_views_are_synchronized(editor, 3)

    editor.remove_segment()
    assert _state(editor) == baseline
    _assert_views_are_synchronized(editor, 2)
    editor.undo()
    assert _state(editor) == added_state
    _assert_views_are_synchronized(editor, 3)
    editor.undo()
    assert _state(editor) == baseline
    _assert_views_are_synchronized(editor, 0)
    editor.redo()
    editor.redo()
    assert _state(editor) == baseline

    editor.segment_list.clearSelection()
    editor.segment_list.item(0).setSelected(True)
    editor.segment_list.item(1).setSelected(True)
    editor.merge_segments()
    merged_state = _state(editor)
    assert len(merged_state) == 2
    assert merged_state[0]["original_text"] == "One\nTwo"
    _assert_views_are_synchronized(editor, 0)

    editor.undo()
    assert _state(editor) == baseline
    _assert_views_are_synchronized(editor, 2)
    editor.redo()
    assert _state(editor) == merged_state
    _assert_views_are_synchronized(editor, 0)

    editor.current_position = 0.75
    editor.split_segment()
    split_state = _state(editor)
    assert len(split_state) == 3
    assert split_state[0]["end_time"] == pytest.approx(0.75)
    assert split_state[1]["start_time"] == pytest.approx(0.75)
    _assert_views_are_synchronized(editor, 0)

    editor.undo()
    assert _state(editor) == merged_state
    _assert_views_are_synchronized(editor, 0)
    editor.redo()
    assert _state(editor) == split_state
    _assert_views_are_synchronized(editor, 0)


def test_main_window_actions_track_stack_and_project_load_clears_it(
    tmp_path, qtbot, monkeypatch
):
    config = AppConfig()
    manager = type(
        "Manager",
        (),
        {"config": config, "add_recent_file": lambda self, _path: None},
    )()
    monkeypatch.setattr(main_window_module, "get_config_manager", lambda: manager)

    window = MainWindow(config, TempFileManager(base_dir=str(tmp_path / "temp")))
    qtbot.addWidget(window)
    editor = window.subtitle_editor_widget
    editor.subtitle_timer.stop()
    editor.segments = _segments()
    editor._sync_processor_segments()
    editor.populate_segment_list()
    editor.clear_undo_history()
    editor.segment_list.setCurrentRow(0)
    window.stacked_widget.setCurrentIndex(2)

    assert not window.undo_action.isEnabled()
    assert not window.redo_action.isEnabled()
    QTest.keyClicks(editor.original_text_edit, " changed")
    assert window.undo_action.isEnabled()
    assert not window.redo_action.isEnabled()

    window.undo()
    assert not window.undo_action.isEnabled()
    assert window.redo_action.isEnabled()
    window.stacked_widget.setCurrentIndex(0)
    assert not window.undo_action.isEnabled()
    assert not window.redo_action.isEnabled()
    window.stacked_widget.setCurrentIndex(2)
    assert not window.undo_action.isEnabled()
    assert window.redo_action.isEnabled()

    video_path = tmp_path / "project-video.mp4"
    video_path.touch()
    project_path = tmp_path / "project.vtp"
    project_path.write_text(
        json.dumps(
            {
                "schema": "videotranslator.project",
                "version": 2,
                "video_path": str(video_path),
                "video_path_relative": video_path.name,
                "segments": [asdict(_segments()[0])],
            }
        ),
        encoding="utf-8",
    )
    window._set_unsaved_changes(False)
    original_load_data = editor.load_data

    def load_without_media(path, data):
        original_load_data(path, data)
        editor.subtitle_timer.stop()

    monkeypatch.setattr(editor, "load_data", load_without_media)
    monkeypatch.setattr(editor, "_prepare_video_playback", lambda *_args: None)
    monkeypatch.setattr(editor, "_apply_aspect_ratio", lambda: None)
    window.open_project_file(str(project_path))

    assert editor.undo_stack.isClean()
    assert editor.undo_stack.count() == 0
    assert not window.undo_action.isEnabled()
    assert not window.redo_action.isEnabled()
    assert _state(editor) == [asdict(_segments()[0])]
    assert editor.segment_list.currentRow() == -1


def test_loading_and_selection_do_not_create_commands(qtbot, tmp_path):
    editor = _editor(qtbot)
    editor.segment_list.setCurrentRow(1)
    editor.segment_list.setCurrentRow(2)
    assert editor.undo_stack.count() == 0

    video_path = tmp_path / "video.mp4"
    video_path.touch()
    editor._prepare_video_playback = lambda *_args: None
    editor._apply_aspect_ratio = lambda: None
    editor.load_data(
        str(video_path),
        {"video_path": str(video_path), "segments": [asdict(_segments()[0])]},
    )
    assert editor.undo_stack.count() == 0
    assert not editor.undo_stack.canUndo()
    assert _state(editor) == [asdict(_segments()[0])]
