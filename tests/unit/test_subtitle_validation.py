"""Subtitle validation model and navigation contracts."""

import math

import pytest

pytest.importorskip("PyQt5")

from PyQt5.QtWidgets import QApplication, QDialog

from app.core.subtitle import SubtitleProcessor, SubtitleSegment
from app.gui.subtitle_editor import SubtitleEditor, SubtitleValidationDialog


@pytest.fixture(scope="module")
def qapp():
    return QApplication.instance() or QApplication([])


@pytest.fixture
def processor(monkeypatch):
    monkeypatch.setattr(SubtitleProcessor, "_validate_dependencies", lambda self: None)
    return SubtitleProcessor()


def test_validator_reports_stable_codes_and_handles_invalid_ranges(processor):
    processor.segments = [
        SubtitleSegment(0.0, 2.0, "first", "", 1),
        SubtitleSegment(1.0, 0.5, "second", "", 2),
        SubtitleSegment(1.5, 1.6, "  ", "\n", 3),
        SubtitleSegment(math.nan, 4.0, "invalid", "", 4),
    ]

    issues = processor.validate_subtitles()
    issue_pairs = {(issue["segment_idx"], issue["code"]) for issue in issues}

    assert (1, "invalid_range") in issue_pairs
    assert (1, "overlap") in issue_pairs
    assert (2, "very_short") in issue_pairs
    assert (2, "empty_text") in issue_pairs
    assert (3, "non_finite_timing") in issue_pairs


def test_validation_dialog_activates_selected_segment(qapp):
    issues = [
        {
            "type": "warning",
            "code": "overlap",
            "message": "details",
            "segment_idx": 2,
        }
    ]
    dialog = SubtitleValidationDialog(issues)
    activated = []
    dialog.issueActivated.connect(activated.append)

    dialog._activate_current()

    assert activated == [2]
    assert dialog.result() == QDialog.Accepted
    assert "1 个问题" in dialog.summary_label.text()


def test_editor_shows_results_and_can_jump_to_problem(
    qapp, processor, monkeypatch
):
    processor.segments = [
        SubtitleSegment(0.0, 1.0, "one", "", 1),
        SubtitleSegment(0.5, 2.0, "two", "", 2),
    ]
    editor = SubtitleEditor("", processor)
    monkeypatch.setattr(SubtitleValidationDialog, "exec", lambda self: QDialog.Rejected)
    try:
        editor.validate_subtitles()

        assert editor._validation_dialog.issue_list.count() == 1
        assert "1 个问题" in editor.status_bar.text()

        editor._focus_validation_issue(1)
        assert editor.segment_list.currentRow() == 1
        assert "第 2 个" in editor.status_bar.text()
    finally:
        editor.close()
