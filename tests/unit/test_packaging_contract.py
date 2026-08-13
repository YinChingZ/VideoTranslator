"""Dependency-light tests for packaging and repository engineering contracts."""

from __future__ import annotations

import ast
import re
import subprocess
import sys
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PYPROJECT_PATH = ROOT / "pyproject.toml"
REQUIREMENTS_PATH = ROOT / "requirements.txt"
MANIFEST_PATH = ROOT / "MANIFEST.in"
_DIST_NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*")


def _metadata() -> dict:
    with PYPROJECT_PATH.open("rb") as stream:
        return tomllib.load(stream)


def _canonical_distribution_names(requirements: list[str]) -> set[str]:
    names = set()
    for requirement in requirements:
        match = _DIST_NAME.match(requirement.strip())
        assert match, f"Cannot parse dependency name: {requirement!r}"
        names.add(re.sub(r"[-_.]+", "-", match.group()).lower())
    return names


def test_build_metadata_and_gui_entry_point() -> None:
    metadata = _metadata()

    assert metadata["build-system"]["build-backend"] == "setuptools.build_meta"
    assert metadata["build-system"]["requires"] == ["setuptools>=77"]
    assert metadata["project"]["requires-python"].startswith(">=3.11")
    assert metadata["project"]["gui-scripts"]["video-translator"] == "main:main"
    assert metadata["tool"]["setuptools"]["py-modules"] == ["main"]
    assert metadata["tool"]["setuptools"]["packages"]["find"]["namespaces"] is True


def test_declared_dependencies_cover_imported_runtime() -> None:
    metadata = _metadata()
    runtime = _canonical_distribution_names(metadata["project"]["dependencies"])
    speech = _canonical_distribution_names(metadata["project"]["optional-dependencies"]["speech"])
    media = _canonical_distribution_names(metadata["project"]["optional-dependencies"]["media"])
    playback = _canonical_distribution_names(
        metadata["project"]["optional-dependencies"]["playback"]
    )

    assert {
        "chardet",
        "ffmpeg-python",
        "keyring",
        "numpy",
        "psutil",
        "pyqt5",
        "pysrt",
        "requests",
        "soundfile",
        "webvtt-py",
    } <= runtime
    assert "openai" not in runtime
    assert {"openai-whisper", "torch"} <= speech
    assert {"librosa", "pydub"} <= media
    assert {"python-vlc"} <= playback
    assert "opencv-python" not in playback


def test_complete_requirements_cover_project_and_full_extras() -> None:
    metadata = _metadata()
    requirement_lines = [
        line.strip()
        for line in REQUIREMENTS_PATH.read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    ]
    complete = _canonical_distribution_names(requirement_lines)
    declared = _canonical_distribution_names(metadata["project"]["dependencies"])
    declared |= _canonical_distribution_names(metadata["project"]["optional-dependencies"]["full"])

    assert declared <= complete


def test_no_declared_dependency_is_only_an_unimplemented_placeholder() -> None:
    metadata = _metadata()
    extras = metadata["project"]["optional-dependencies"]
    all_declared = _canonical_distribution_names(metadata["project"]["dependencies"])
    for dependencies in extras.values():
        all_declared |= _canonical_distribution_names(dependencies)

    assert "local-translation" not in extras
    assert "transformers" not in all_declared
    assert "openai" not in all_declared


def test_package_version_matches_application_version() -> None:
    metadata = _metadata()
    config_tree = ast.parse((ROOT / "app/config.py").read_text(encoding="utf-8"))
    version = next(
        node.value.value
        for node in config_tree.body
        if isinstance(node, ast.Assign)
        and any(isinstance(target, ast.Name) and target.id == "APP_VERSION" for target in node.targets)
        and isinstance(node.value, ast.Constant)
    )

    assert metadata["project"]["version"] == version


def test_license_and_package_discovery_are_explicit() -> None:
    metadata = _metadata()
    project = metadata["project"]
    package_finder = metadata["tool"]["setuptools"]["packages"]["find"]

    assert project["license"] == "MIT"
    assert project["license-files"] == ["LICENSE"]
    assert (ROOT / "LICENSE").is_file()
    assert package_finder["include"] == ["app*"]
    assert {"tests*", "docs*", "model*", "scripts*"} <= set(package_finder["exclude"])

    manifest = MANIFEST_PATH.read_text(encoding="utf-8")
    assert "recursive-include app *.py" in manifest
    assert {"prune tests", "prune docs", "prune model", "prune scripts"} <= set(
        manifest.splitlines()
    )


def test_default_pytest_collection_excludes_historical_script_suites() -> None:
    pytest_config = _metadata()["tool"]["pytest"]["ini_options"]

    assert pytest_config["testpaths"] == ["tests/unit"]
    assert pytest_config["python_files"] == ["test_*.py"]


def test_organization_check_is_independent_of_working_directory(tmp_path: Path) -> None:
    result = subprocess.run(
        [sys.executable, str(ROOT / "scripts/verify_organization.py"), "--quiet"],
        cwd=tmp_path,
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stdout + result.stderr
