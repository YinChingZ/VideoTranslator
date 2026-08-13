"""Audit a built wheel using only the Python standard library.

This is intentionally a standalone release gate rather than a pytest test: CI
passes the exact artifact it will distribute, so stale build directories cannot
make a source-tree-only test pass.
"""

from __future__ import annotations

import argparse
import base64
import csv
import hashlib
import io
import re
import sys
import tomllib
import zipfile
from email.parser import BytesParser
from email.policy import default
from pathlib import Path, PurePosixPath

ROOT = Path(__file__).resolve().parents[2]
FORBIDDEN_PARTS = {
    ".coverage",
    ".env",
    ".git",
    ".mypy_cache",
    ".pytest_cache",
    ".ruff_cache",
    "__pycache__",
    "build",
    "docs",
    "model",
    "models",
    "scripts",
    "tests",
}
FORBIDDEN_SUFFIXES = {
    ".bin",
    ".db",
    ".env",
    ".key",
    ".onnx",
    ".p12",
    ".pem",
    ".pfx",
    ".pt",
    ".pth",
    ".pyc",
    ".safetensors",
    ".sqlite",
    ".sqlite3",
}
FORBIDDEN_NAMES = {
    ".DS_Store",
    "config.json",
    "credentials.json",
    "secrets.json",
}
REQUIRED_MODULES = {
    "main.py",
    "app/__init__.py",
    "app/config.py",
    "app/core/audio.py",
    "app/core/speech.py",
    "app/core/subtitle.py",
    "app/core/translation.py",
    "app/core/video.py",
    "app/gui/main_window.py",
    "app/gui/processing.py",
    "app/gui/subtitle_editor.py",
    "app/gui/video_export_thread.py",
    "app/gui/video_import.py",
    "app/utils/checkpoint.py",
    "app/utils/paths.py",
    "app/utils/system_health_checker.py",
}


def _project_metadata() -> dict:
    with (ROOT / "pyproject.toml").open("rb") as stream:
        return tomllib.load(stream)


def _distribution_name(requirement: str) -> str:
    match = re.match(r"[A-Za-z0-9][A-Za-z0-9._-]*", requirement)
    if not match:
        raise AssertionError(f"Cannot parse dependency name: {requirement!r}")
    return re.sub(r"[-_.]+", "-", match.group()).lower()


def _assert_safe_members(names: list[str]) -> None:
    assert len(names) == len(set(names)), "wheel contains duplicate archive members"
    for name in names:
        path = PurePosixPath(name)
        assert not path.is_absolute(), f"absolute archive path: {name}"
        assert ".." not in path.parts, f"parent traversal in archive path: {name}"
        assert not (set(path.parts) & FORBIDDEN_PARTS), f"forbidden wheel member: {name}"
        assert not any(part.endswith(".egg-info") for part in path.parts)
        assert path.name not in FORBIDDEN_NAMES, f"sensitive wheel member: {name}"
        assert path.suffix.lower() not in FORBIDDEN_SUFFIXES, f"forbidden wheel member: {name}"
        assert not name.endswith(("~", ".bak", ".backup", ".tmp")), (
            f"temporary/backup file in wheel: {name}"
        )


def _assert_record_integrity(archive: zipfile.ZipFile, names: list[str], dist_info: str) -> None:
    record_name = f"{dist_info}/RECORD"
    rows = list(csv.reader(io.StringIO(archive.read(record_name).decode("utf-8"))))
    records = {path: (digest, size) for path, digest, size in rows}

    assert len(rows) == len(records), "RECORD contains duplicate paths"
    assert set(records) == set(names), "RECORD does not describe every wheel member exactly once"
    for name in names:
        digest, size = records[name]
        if name == record_name:
            assert digest == "" and size == ""
            continue
        payload = archive.read(name)
        expected = base64.urlsafe_b64encode(hashlib.sha256(payload).digest()).rstrip(b"=")
        assert digest == f"sha256={expected.decode('ascii')}", f"bad RECORD hash: {name}"
        assert size == str(len(payload)), f"bad RECORD size: {name}"


def audit_wheel(wheel_path: Path) -> None:
    project = _project_metadata()["project"]
    expected_stem = project["name"].replace("-", "_")
    assert wheel_path.name == f"{expected_stem}-{project['version']}-py3-none-any.whl"

    with zipfile.ZipFile(wheel_path) as archive:
        names = archive.namelist()
        _assert_safe_members(names)
        assert REQUIRED_MODULES <= set(names), "wheel is missing required application modules"
        source_modules = {
            path.relative_to(ROOT).as_posix()
            for path in (ROOT / "app").rglob("*.py")
            if "__pycache__" not in path.parts
        }
        wheel_modules = {
            name for name in names if name.startswith("app/") and name.endswith(".py")
        }
        assert wheel_modules == source_modules, (
            "wheel application modules differ from the source tree: "
            f"missing={sorted(source_modules - wheel_modules)}, "
            f"unexpected={sorted(wheel_modules - source_modules)}"
        )
        empty_modules = {
            name
            for name in wheel_modules
            if not archive.read(name) and PurePosixPath(name).name != "__init__.py"
        }
        assert not empty_modules, f"empty placeholder modules in wheel: {sorted(empty_modules)}"

        dist_infos = {name.split("/", 1)[0] for name in names if ".dist-info/" in name}
        assert len(dist_infos) == 1, "wheel must contain exactly one .dist-info directory"
        dist_info = dist_infos.pop()
        _assert_record_integrity(archive, names, dist_info)

        wheel_metadata = archive.read(f"{dist_info}/WHEEL").decode("utf-8")
        assert "Root-Is-Purelib: true" in wheel_metadata
        assert "Tag: py3-none-any" in wheel_metadata

        entry_points = archive.read(f"{dist_info}/entry_points.txt").decode("utf-8")
        assert entry_points.strip() == "[gui_scripts]\nvideo-translator = main:main"

        metadata = BytesParser(policy=default).parsebytes(archive.read(f"{dist_info}/METADATA"))
        assert metadata["Name"] == project["name"]
        assert metadata["Version"] == project["version"]
        assert metadata["Requires-Python"] == project["requires-python"]
        assert metadata["License-Expression"] == "MIT"
        assert metadata.get_all("License-File") == ["LICENSE"]

        requirements = metadata.get_all("Requires-Dist", failobj=[])
        base_requirements = [item for item in requirements if "; extra ==" not in item]
        base_names = {_distribution_name(item) for item in base_requirements}
        all_names = {_distribution_name(item) for item in requirements}
        assert "openai" not in base_names, "unused OpenAI SDK leaked into base installation"
        assert "openai" not in all_names
        assert "transformers" not in all_names
        assert {"openai-whisper", "torch"}.isdisjoint(base_names)
        assert {"opencv-python", "python-vlc"}.isdisjoint(base_names)
        assert {"librosa", "pydub", "transformers"}.isdisjoint(base_names)
        assert "opencv-python" not in all_names, "unused OpenCV dependency leaked into wheel"

        license_members = [name for name in names if name.endswith("/licenses/LICENSE")]
        assert len(license_members) == 1
        assert archive.read(license_members[0]) == (ROOT / "LICENSE").read_bytes()

        # These paths remain only as compatibility shims. They may adapt old
        # call signatures, but they must not contain another HTTP/provider
        # implementation or become a second source of truth.
        for legacy_name in (
            "app/core/translation_new.py",
            "app/core/translation_original.py",
        ):
            if legacy_name in names:
                legacy_source = archive.read(legacy_name).decode("utf-8")
                assert len(legacy_source) < 10_000, (
                    f"historical implementation was packaged instead of a shim: {legacy_name}"
                )
                assert "from .translation import" in legacy_source
                assert "import requests" not in legacy_source
                assert "api.openai.com" not in legacy_source
                assert "deepl.com" not in legacy_source
                assert "translation.googleapis.com" not in legacy_source


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("wheel", type=Path, nargs="+")
    args = parser.parse_args(argv)
    assert len(args.wheel) == 1, f"expected one wheel, found {len(args.wheel)}"
    audit_wheel(args.wheel[0].resolve())
    print(f"Wheel audit passed: {args.wheel[0].name}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except AssertionError as error:
        print(f"Wheel audit failed: {error}", file=sys.stderr)
        raise SystemExit(1) from error
