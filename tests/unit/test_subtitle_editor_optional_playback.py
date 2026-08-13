"""字幕编辑器可选播放后端与列表操作回归测试。"""

import os
import subprocess
import sys

import pytest


os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

pytest.importorskip("PyQt5")

from PyQt5.QtCore import QItemSelectionModel
from PyQt5.QtGui import QKeySequence
from PyQt5.QtWidgets import QApplication, QAbstractItemView, QShortcut

from app.core.subtitle import SubtitleProcessor
from app.gui.subtitle_editor import SubtitleEditor


@pytest.fixture(scope="module")
def qapp():
    return QApplication.instance() or QApplication([])


def _make_editor():
    processor = SubtitleProcessor()
    processor.create_from_segments([
        {
            "start": 0.0,
            "end": 2.0,
            "original_text": "one",
            "translated_text": "一",
        },
        {
            "start": 2.0,
            "end": 4.0,
            "original_text": "two",
            "translated_text": "二",
        },
        {
            "start": 4.0,
            "end": 6.0,
            "original_text": "three",
            "translated_text": "三",
        },
    ])
    return SubtitleEditor("", processor)


def test_module_import_does_not_eagerly_import_optional_backends():
    """即使 VLC 不可用，模块导入也不应触碰它。"""
    code = (
        "import sys; "
        "import app.gui.subtitle_editor as module; "
        "assert module.vlc is None; "
        "assert module._vlc_import_checked is False; "
        "assert 'cv2' not in sys.modules"
    )
    env = os.environ.copy()
    env["QT_QPA_PLATFORM"] = "offscreen"
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    result = subprocess.run(
        [sys.executable, "-c", code],
        cwd=os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")),
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr


def test_editor_enables_extended_selection_and_safe_shortcuts(qapp):
    editor = _make_editor()
    try:
        assert editor.segment_list.selectionMode() == QAbstractItemView.ExtendedSelection
        assert editor.segment_list.accessibleName() == "字幕片段列表"

        shortcuts = {
            shortcut.key().toString(QKeySequence.PortableText)
            for shortcut in editor.findChildren(QShortcut)
        }
        assert "Ctrl+S" not in shortcuts
        assert "Ctrl+E" not in shortcuts
        assert "Ctrl+Shift+K" in shortcuts
        assert "Ctrl+Shift+E" in shortcuts
    finally:
        editor.close()


def test_merge_and_split_keep_editor_on_processor_canonical_list(qapp):
    editor = _make_editor()
    try:
        selection_model = editor.segment_list.selectionModel()
        selection_model.select(
            editor.segment_list.model().index(0, 0),
            QItemSelectionModel.Select,
        )
        selection_model.select(
            editor.segment_list.model().index(1, 0),
            QItemSelectionModel.Select,
        )

        editor.merge_segments()

        assert editor.segments is editor.subtitle_processor.segments
        assert len(editor.segments) == 2
        assert editor.segments[0].original_text == "one\ntwo"
        assert editor.segment_list.count() == 2

        editor.segment_list.setCurrentRow(0)
        editor.current_position = 1.0
        editor.split_segment()

        assert editor.segments is editor.subtitle_processor.segments
        assert len(editor.segments) == 3
        assert editor.segment_list.count() == 3
        assert editor.segments[0].end_time == pytest.approx(1.0)
        assert editor.segments[1].start_time == pytest.approx(1.0)
    finally:
        editor.close()
