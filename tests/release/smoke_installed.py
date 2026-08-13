"""Smoke-test the installed base wheel without importing from the checkout."""

from __future__ import annotations

import importlib.util
import os
import sys
import tempfile
import tomllib
from importlib import metadata
from pathlib import Path

SOURCE_ROOT = Path(__file__).resolve().parents[2]
with (SOURCE_ROOT / "pyproject.toml").open("rb") as _project_file:
    EXPECTED_VERSION = tomllib.load(_project_file)["project"]["version"]
OPTIONAL_DISTRIBUTIONS = {
    "librosa",
    "openai",
    "openai-whisper",
    "opencv-python",
    "pydub",
    "python-vlc",
    "torch",
    "transformers",
}
IMPORT_TARGETS = (
    "app.config",
    "app.core.audio",
    "app.core.speech",
    "app.core.subtitle",
    "app.core.translation",
    "app.core.video",
    "app.gui.export_dialog",
    "app.gui.main_window",
    "app.gui.processing",
    "app.gui.subtitle_editor",
    "app.gui.video_import",
    "app.utils.checkpoint",
    "app.utils.paths",
    "app.utils.system_health_checker",
)


def main() -> int:
    # Running a script normally prepends its source directory. Remove every
    # checkout path so imports prove the wheel, not the working tree, works.
    source_root = SOURCE_ROOT.resolve()
    sys.path[:] = [
        entry
        for entry in sys.path
        if entry and not Path(entry).resolve().is_relative_to(source_root)
    ]

    with tempfile.TemporaryDirectory(prefix="video-translator-smoke-") as temp_dir:
        os.environ.update(
            {
                "HOME": temp_dir,
                "USERPROFILE": temp_dir,
                "XDG_CACHE_HOME": str(Path(temp_dir) / "cache"),
                "XDG_CONFIG_HOME": str(Path(temp_dir) / "config"),
                "QT_QPA_PLATFORM": "offscreen",
                "PYTHON_KEYRING_BACKEND": "keyring.backends.null.Keyring",
            }
        )

        distribution = metadata.distribution("video-translator")
        assert distribution.version == EXPECTED_VERSION
        installed_names = {
            distribution.metadata["Name"].lower().replace("_", "-")
            for distribution in metadata.distributions()
        }
        assert OPTIONAL_DISTRIBUTIONS.isdisjoint(installed_names)

        entry_points = [
            entry
            for entry in distribution.entry_points
            if entry.group == "gui_scripts" and entry.name == "video-translator"
        ]
        assert len(entry_points) == 1
        assert entry_points[0].value == "main:main"
        entry_callable = entry_points[0].load()
        assert callable(entry_callable)
        entry_module = sys.modules[entry_callable.__module__]
        assert not Path(entry_module.__file__).resolve().is_relative_to(source_root)

        for module_name in IMPORT_TARGETS:
            module = __import__(module_name, fromlist=["*"])
            module_file = Path(module.__file__).resolve()
            assert not module_file.is_relative_to(source_root), (
                f"{module_name} was imported from the checkout: {module_file}"
            )

        # Optional imports are guarded and must remain unavailable in the base
        # environment even after importing every production module above.
        assert importlib.util.find_spec("whisper") is None
        assert importlib.util.find_spec("cv2") is None
        assert importlib.util.find_spec("vlc") is None

    print("Installed base-wheel smoke test passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
