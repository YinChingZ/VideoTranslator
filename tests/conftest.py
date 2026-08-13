"""Shared pytest isolation for the legacy and production test suites."""

from __future__ import annotations

import atexit
import os
import tempfile
from pathlib import Path

import pytest

# Several legacy tests construct ConfigManager during module import. Redirect
# those writes away from the developer's real home before collection starts.
_TEST_HOME = tempfile.TemporaryDirectory(prefix="video-translator-tests-")
atexit.register(_TEST_HOME.cleanup)
os.environ["HOME"] = _TEST_HOME.name
os.environ["USERPROFILE"] = _TEST_HOME.name
os.environ["XDG_CONFIG_HOME"] = os.path.join(_TEST_HOME.name, ".config")
os.environ["XDG_CACHE_HOME"] = os.path.join(_TEST_HOME.name, ".cache")
os.environ["XDG_STATE_HOME"] = os.path.join(_TEST_HOME.name, ".state")

# Qt can create widgets in CI without a display server.
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("MPLBACKEND", "Agg")
os.environ.setdefault("PYTHON_KEYRING_BACKEND", "keyring.backends.null.Keyring")

# These files are historical manual-verification scripts, despite their names.
# Several swallow exceptions, return booleans from test functions, invoke real
# media backends, or only reimplement production logic. Keep them available for
# forensic/manual runs without allowing them to create a false-green default
# pytest result. New test modules are collected automatically unless explicitly
# added here after review.
LEGACY_TEST_MODULES = frozenset(
    {
        "test_appconfig_setdefault_fix.py",
        "test_audio_fix.py",
        "test_burn_complete.py",
        "test_burn_subtitles_fix.py",
        "test_checkpoint_fix.py",
        "test_complete_integration.py",
        "test_config.py",
        "test_config_import.py",
        "test_core_functionality.py",
        "test_embed_subtitles.py",
        "test_export_dialog_fix.py",
        "test_export_video_fix.py",
        "test_force_reload.py",
        "test_full_export.py",
        "test_get_method.py",
        "test_gui_integration.py",
        "test_imports.py",
        "test_improved_processing.py",
        "test_memory_manager_fix.py",
        "test_model_loading_fix.py",
        "test_settings_dialog_fix.py",
        "test_simple_path.py",
        "test_subprocess_burn.py",
        "test_subtitle_editor_fix.py",
        "test_subtitle_error_fix.py",
        "test_subtitle_fix.py",
        "test_subtitle_fix_simple.py",
        "test_timeline_compatibility.py",
        "test_translation_subtitle_fix.py",
        "test_translator_fix.py",
        "test_ui_fixes.py",
        "test_undo_redo.py",
        "test_undo_redo_practical.py",
        "test_undo_redo_progress.py",
        "test_undo_redo_progress_fixed.py",
        "test_undo_redo_simple.py",
        "test_video_switching_fix.py",
        "test_vlc_embedding_fix.py",
        "test_vlc_subtitle_fix.py",
        "test_vlc_video_switching.py",
    }
)


def pytest_ignore_collect(collection_path: Path, config: pytest.Config) -> bool | None:
    """Exclude manual legacy scripts unless a developer explicitly opts in."""

    del config
    if os.environ.get("VIDEO_TRANSLATOR_RUN_LEGACY_TESTS") == "1":
        return None
    if collection_path.parent.name == "unit" and collection_path.name in LEGACY_TEST_MODULES:
        return True
    return None
