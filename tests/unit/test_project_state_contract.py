"""Regression tests for project, settings, and main-window state contracts."""

from __future__ import annotations

import json
import os
import shutil
import sys
from pathlib import Path

import pytest

pytest.importorskip("PyQt5")

from PyQt5.QtGui import QCloseEvent
from PyQt5.QtWidgets import QApplication, QDialog

from app import config as config_module
from app.config import ConfigManager
from app.core.subtitle import SubtitleSegment
from app.gui import main_window as main_window_module
from app.gui.main_window import MainWindow, SettingsDialog
from app.utils.temp_files import TempFileManager


@pytest.fixture(scope="module")
def qapp():
    return QApplication.instance() or QApplication([])


@pytest.fixture
def isolated_manager(tmp_path, monkeypatch):
    class MemoryKeyring:
        def __init__(self):
            self.values = {}

        def get_password(self, service, username):
            return self.values.get((service, username))

        def set_password(self, service, username, password):
            self.values[(service, username)] = password

        def delete_password(self, service, username):
            self.values.pop((service, username), None)

    monkeypatch.setitem(sys.modules, "keyring", MemoryKeyring())
    manager = ConfigManager(tmp_path / "settings" / "config.json")
    monkeypatch.setattr(main_window_module, "get_config_manager", lambda: manager)
    return manager


def _window(tmp_path: Path, qapp, manager: ConfigManager) -> MainWindow:
    del qapp
    return MainWindow(
        manager.config,
        TempFileManager(base_dir=str(tmp_path / "application-temp")),
    )


def _segment() -> SubtitleSegment:
    return SubtitleSegment(
        start_time=0.0,
        end_time=1.25,
        original_text="Hello",
        translated_text="你好",
        index=1,
    )


def test_settings_keeps_provider_drafts_and_persists_theme(
    tmp_path, qapp, isolated_manager
):
    del tmp_path, qapp
    manager = isolated_manager
    assert manager.set_api_key("openai", "openai-original", save_config=False)
    assert manager.set_api_key("deepl", "deepl-original", save_config=False)

    dialog = SettingsDialog(manager, manager.config)
    try:
        dialog.api_edit.setText("openai-edited")
        dialog.provider_combo.setCurrentText("deepl")
        dialog.api_edit.setText("deepl-edited")
        dialog.provider_combo.setCurrentText("openai")

        assert dialog.api_edit.text() == "openai-edited"
        dialog.theme_combo.setCurrentIndex(dialog.theme_combo.findData("dark"))
        dialog.accept()

        assert dialog.result() == QDialog.Accepted
        assert manager.config.translation_provider == "openai"
        assert manager.config.theme == "dark"
        assert manager.get_api_key("openai") == "openai-edited"
        assert manager.get_api_key("deepl") == "deepl-edited"
    finally:
        dialog.close()


def test_settings_cancel_does_not_mutate_keys(tmp_path, qapp, isolated_manager):
    del tmp_path, qapp
    manager = isolated_manager
    assert manager.set_api_key("openai", "saved-key", save_config=False)

    dialog = SettingsDialog(manager, manager.config)
    try:
        dialog.api_edit.setText("discard-me")
        dialog.provider_combo.setCurrentText("google")
        dialog.api_edit.setText("also-discard-me")
        dialog.reject()

        assert manager.get_api_key("openai") == "saved-key"
        assert manager.get_api_key("google") == ""
    finally:
        dialog.close()


def test_show_settings_applies_accepted_theme_immediately(
    tmp_path, qapp, isolated_manager, monkeypatch
):
    window = _window(tmp_path, qapp, isolated_manager)

    class AcceptedSettings:
        def __init__(self, manager, config, parent):
            del manager, parent
            config.theme = "dark"

        def exec(self):
            return QDialog.Accepted

    monkeypatch.setattr(main_window_module, "SettingsDialog", AcceptedSettings)
    try:
        window.show_settings()
        assert window.style_manager.requested_theme == "dark"
        assert window.style_manager.current_theme == "dark"
        assert window.icon_manager.current_theme == "dark"
        assert not window.open_action.icon().isNull()
    finally:
        window.close()


def test_v2_project_is_atomic_portable_and_keeps_path_roles_distinct(
    tmp_path, qapp, isolated_manager, monkeypatch
):
    bundle = tmp_path / "bundle"
    media = bundle / "media"
    media.mkdir(parents=True)
    video = media / "clip.mp4"
    video.write_bytes(b"not-real-media")
    project = bundle / "session.vtp"

    window = _window(tmp_path, qapp, isolated_manager)
    try:
        window.current_video_path = str(video)
        window.current_file_path = str(video)
        window.workflow.set_data("video_path", str(video))
        window.workflow.set_data("source_language", "en")
        window.workflow.set_data("target_language", "zh-CN")
        window.stacked_widget.setCurrentIndex(2)
        monkeypatch.setattr(
            window.subtitle_editor_widget,
            "get_processed_segments",
            lambda: [_segment()],
        )
        window.mark_unsaved_changes()

        assert window.save_project(str(project)) is True
        payload = json.loads(project.read_text(encoding="utf-8"))
        assert payload["schema"] == "videotranslator.project"
        assert payload["version"] == 2
        assert payload["video_path"] == str(video.resolve())
        assert payload["video_path_relative"] == os.path.join("media", "clip.mp4")
        assert payload["source_language"] == "en"
        assert payload["target_language"] == "zh-CN"
        assert window.current_video_path == str(video)
        assert window.current_file_path == str(video)
        assert window.current_project_path == str(project.resolve())
        assert not window.has_unsaved_changes
        assert not window.windowTitle().endswith(" *")
        assert list(bundle.glob(".session.vtp.*.tmp")) == []
    finally:
        window.close()

    moved = tmp_path / "moved-bundle"
    shutil.move(str(bundle), moved)
    moved_project = moved / "session.vtp"
    moved_video = moved / "media" / "clip.mp4"
    loaded = {}
    reopened = _window(tmp_path / "second", qapp, isolated_manager)
    monkeypatch.setattr(
        reopened.subtitle_editor_widget,
        "load_data",
        lambda path, data: loaded.update(path=path, data=data),
    )
    try:
        reopened.open_project_file(str(moved_project))

        assert reopened.current_video_path == str(moved_video.resolve())
        assert reopened.current_file_path == str(moved_video.resolve())
        assert reopened.current_project_path == str(moved_project.resolve())
        assert reopened.workflow.get_data("video_path") == str(moved_video.resolve())
        assert loaded["path"] == str(moved_video.resolve())
        assert loaded["data"]["segments"][0]["translated_text"] == "你好"
        assert reopened.windowTitle().count("*") == 0
        assert reopened.windowTitle().endswith("[项目: session.vtp]")
    finally:
        reopened.close()


def test_legacy_segment_list_uses_current_video(
    tmp_path, qapp, isolated_manager, monkeypatch
):
    video = tmp_path / "legacy.mp4"
    video.write_bytes(b"video")
    project = tmp_path / "legacy.vtp"
    project.write_text(
        json.dumps(
            [
                {
                    "start": 0,
                    "end": 1,
                    "original": "Legacy",
                    "translation": "旧版",
                }
            ]
        ),
        encoding="utf-8",
    )
    loaded = {}
    window = _window(tmp_path, qapp, isolated_manager)
    window.current_video_path = str(video)
    monkeypatch.setattr(
        window.subtitle_editor_widget,
        "load_data",
        lambda path, data: loaded.update(path=path, data=data),
    )
    try:
        window.open_project_file(str(project))
        assert loaded["path"] == str(video)
        assert loaded["data"]["segments"][0]["translation"] == "旧版"
        assert window.current_project_path == str(project.resolve())
    finally:
        window.close()


def test_unsaved_marker_is_derived_and_failed_open_has_no_recent_side_effect(
    tmp_path, qapp, isolated_manager, monkeypatch
):
    first = tmp_path / "first.mp4"
    second = tmp_path / "second.mp4"
    first.write_bytes(b"first")
    second.write_bytes(b"second")
    window = _window(tmp_path, qapp, isolated_manager)
    try:
        window.current_video_path = str(first)
        window.current_file_path = str(first)
        window._update_window_title()
        window.mark_unsaved_changes()
        window.mark_unsaved_changes()
        assert window.windowTitle().count("*") == 1

        monkeypatch.setattr(window, "confirm_discard_changes", lambda: False)
        window.open_video(str(second))

        assert window.current_video_path == str(first)
        assert str(second.resolve()) not in isolated_manager.config.recent_files
        assert window.windowTitle().count("*") == 1
    finally:
        window._set_unsaved_changes(False)
        window.close()


def test_failed_atomic_replace_preserves_existing_project(
    tmp_path, qapp, isolated_manager, monkeypatch
):
    video = tmp_path / "clip.mp4"
    video.write_bytes(b"video")
    project = tmp_path / "existing.vtp"
    project.write_text("original", encoding="utf-8")
    window = _window(tmp_path, qapp, isolated_manager)
    window.workflow.set_data("video_path", str(video))
    window.stacked_widget.setCurrentIndex(2)
    window.mark_unsaved_changes()
    monkeypatch.setattr(
        window.subtitle_editor_widget,
        "get_processed_segments",
        lambda: [_segment()],
    )
    monkeypatch.setattr(main_window_module.os, "replace", lambda *args: (_ for _ in ()).throw(OSError("disk error")))
    monkeypatch.setattr(main_window_module.QMessageBox, "warning", lambda *args, **kwargs: None)
    try:
        assert window.save_project(str(project)) is False
        assert project.read_text(encoding="utf-8") == "original"
        assert window.has_unsaved_changes
        assert window.current_project_path is None
        assert list(tmp_path.glob(".existing.vtp.*.tmp")) == []
    finally:
        window._set_unsaved_changes(False)
        window.close()


def test_invalid_config_values_are_normalized(tmp_path, monkeypatch):
    monkeypatch.setitem(sys.modules, "keyring", object())
    path = tmp_path / "config.json"
    path.write_text(
        json.dumps(
            {
                "theme": "ultraviolet",
                "translation_provider": "Unknown",
                "recent_files": "not-a-list",
                "max_recent_files": "bad",
            }
        ),
        encoding="utf-8",
    )

    manager = config_module.ConfigManager(path)

    assert manager.config.theme == "system"
    assert manager.config.translation_provider == "openai"
    assert manager.config.recent_files == []
    assert manager.config.max_recent_files == 10


def test_close_during_processing_cancels_once_then_auto_closes(
    tmp_path, qapp, isolated_manager, monkeypatch
):
    window = _window(tmp_path, qapp, isolated_manager)
    cancelled = []
    questions = []
    window.processing_widget.is_processing = True
    monkeypatch.setattr(
        window.processing_widget,
        "cancel_processing",
        lambda: cancelled.append(True),
    )
    monkeypatch.setattr(
        main_window_module.QMessageBox,
        "question",
        lambda *args, **kwargs: (
            questions.append(args[1]) or main_window_module.QMessageBox.StandardButton.Yes
        ),
    )
    first_event = QCloseEvent()

    window.closeEvent(first_event)

    assert not first_event.isAccepted()
    assert cancelled == [True]
    assert window._close_after_processing_cancel
    assert questions == ["处理仍在进行"]

    second_event = QCloseEvent()
    window.closeEvent(second_event)
    assert not second_event.isAccepted()
    assert cancelled == [True]
    assert questions == ["处理仍在进行"]

    window.processing_widget.is_processing = False
    final_event = QCloseEvent()
    window.closeEvent(final_event)
    assert final_event.isAccepted()
    assert not window._close_after_processing_cancel


def test_finishing_export_close_bypasses_second_unsaved_prompt(
    tmp_path, qapp, isolated_manager, monkeypatch
):
    window = _window(tmp_path, qapp, isolated_manager)
    window.has_unsaved_changes = True
    window._close_after_export_cancel = True
    prompts = []
    monkeypatch.setattr(
        window,
        "confirm_discard_changes",
        lambda: prompts.append(True) or False,
    )

    event = QCloseEvent()
    window.closeEvent(event)

    assert event.isAccepted()
    assert prompts == []
    assert not window._close_after_export_cancel
