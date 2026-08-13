"""Resolve user-writable application paths without touching the source tree."""

from __future__ import annotations

import os
import sys
from pathlib import Path

APP_DIR_NAME = "VideoTranslator"
APP_SLUG = "video-translator"


def _expanded_path(value: str) -> Path:
    """Expand a user-provided path while preserving relative-path semantics."""

    return Path(os.path.expandvars(os.path.expanduser(value))).resolve()


def get_cache_dir() -> Path:
    """Return the platform-appropriate cache root for this application.

    ``VIDEOTRANSLATOR_CACHE_DIR`` is the explicit application override.  The
    XDG variable is honoured on every platform so tests, containers, and
    managed desktop environments can redirect writes deterministically.
    """

    override = os.environ.get("VIDEOTRANSLATOR_CACHE_DIR")
    if override:
        return _expanded_path(override)

    xdg_cache = os.environ.get("XDG_CACHE_HOME")
    if xdg_cache:
        return _expanded_path(xdg_cache) / APP_SLUG

    if sys.platform == "win32":
        local_app_data = os.environ.get("LOCALAPPDATA")
        root = _expanded_path(local_app_data) if local_app_data else Path.home()
        return root / APP_DIR_NAME / "Cache"

    if sys.platform == "darwin":
        return Path.home() / "Library" / "Caches" / APP_DIR_NAME

    return Path.home() / ".cache" / APP_SLUG


def get_state_dir() -> Path:
    """Return a user-writable directory for logs and diagnostic reports."""

    override = os.environ.get("VIDEOTRANSLATOR_STATE_DIR")
    if override:
        return _expanded_path(override)

    xdg_state = os.environ.get("XDG_STATE_HOME")
    if xdg_state:
        return _expanded_path(xdg_state) / APP_SLUG

    if sys.platform == "win32":
        local_app_data = os.environ.get("LOCALAPPDATA")
        root = _expanded_path(local_app_data) if local_app_data else Path.home()
        return root / APP_DIR_NAME

    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / APP_DIR_NAME

    return Path.home() / ".local" / "state" / APP_SLUG


def get_config_dir() -> Path:
    """Return the platform-appropriate directory for persistent settings."""

    override = os.environ.get("VIDEOTRANSLATOR_CONFIG_DIR")
    if override:
        return _expanded_path(override)

    xdg_config = os.environ.get("XDG_CONFIG_HOME")
    if xdg_config:
        return _expanded_path(xdg_config) / APP_SLUG

    if sys.platform == "win32":
        app_data = os.environ.get("APPDATA") or os.environ.get("LOCALAPPDATA")
        root = _expanded_path(app_data) if app_data else Path.home()
        return root / APP_DIR_NAME

    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / APP_DIR_NAME

    return Path.home() / ".config" / APP_SLUG


def get_checkpoint_dir() -> Path:
    """Return the private state directory used for resumable processing."""

    override = os.environ.get("VIDEOTRANSLATOR_CHECKPOINT_DIR")
    if override:
        return _expanded_path(override)
    return get_state_dir() / "checkpoints"


def get_whisper_model_dir() -> Path:
    """Return the writable Whisper download directory.

    The dedicated override is useful when models live on a large secondary
    volume or in a centrally managed cache.
    """

    override = os.environ.get("VIDEOTRANSLATOR_MODEL_DIR")
    if override:
        return _expanded_path(override)
    return get_cache_dir() / "whisper"


def get_transcription_cache_dir() -> Path:
    """Return the cache directory for completed transcription JSON files."""

    return get_cache_dir() / "transcriptions"


def ensure_private_directory(path: Path) -> Path:
    """Create *path* and best-effort restrict it to the current user."""

    path.mkdir(mode=0o700, parents=True, exist_ok=True)
    try:
        path.chmod(0o700)
    except OSError:
        # Windows ACLs and some network file systems do not implement POSIX
        # modes; directory creation is still useful there.
        pass
    return path
