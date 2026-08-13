#!/usr/bin/env python3
"""Validate the repository layout from any operating system or working directory."""

from __future__ import annotations

import argparse
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Sequence


PROJECT_ROOT = Path(__file__).resolve().parents[1]

REQUIRED_DIRECTORIES = (
    "app",
    "app/core",
    "app/gui",
    "app/resources",
    "app/utils",
    "tests",
    "tests/unit",
    "tests/integration",
    "tests/debug",
    "docs",
    "docs/fix-reports",
    "docs/analysis",
    "scripts",
)

REQUIRED_FILES = (
    "README.md",
    "LICENSE",
    "main.py",
    "pyproject.toml",
    "requirements.txt",
    "app/__init__.py",
)


@dataclass
class OrganizationReport:
    """Machine-readable validation result used by the CLI and unit tests."""

    root: Path
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    counts: dict[str, int] = field(default_factory=dict)

    @property
    def ok(self) -> bool:
        return not self.errors


def _nonempty_files(directory: Path, patterns: Sequence[str]) -> list[Path]:
    files = {path for pattern in patterns for path in directory.glob(pattern)}
    return sorted(path for path in files if path.is_file() and path.stat().st_size > 0)


def validate_organization(root: Path = PROJECT_ROOT) -> OrganizationReport:
    """Validate required structure and return all findings without mutating files."""

    root = root.expanduser().resolve()
    report = OrganizationReport(root=root)

    if not root.is_dir():
        report.errors.append(f"Project root does not exist or is not a directory: {root}")
        return report

    for relative_path in REQUIRED_DIRECTORIES:
        if not (root / relative_path).is_dir():
            report.errors.append(f"Missing required directory: {relative_path}")

    for relative_path in REQUIRED_FILES:
        if not (root / relative_path).is_file():
            report.errors.append(f"Missing required file: {relative_path}")

    unit_dir = root / "tests/unit"
    integration_dir = root / "tests/integration"
    debug_dir = root / "tests/debug"
    fix_report_dir = root / "docs/fix-reports"
    analysis_dir = root / "docs/analysis"

    unit_tests = _nonempty_files(unit_dir, ("test_*.py",)) if unit_dir.is_dir() else []
    integration_tests = (
        _nonempty_files(integration_dir, ("test_*.py", "*_test.py"))
        if integration_dir.is_dir()
        else []
    )
    debug_scripts = _nonempty_files(debug_dir, ("*.py",)) if debug_dir.is_dir() else []
    fix_reports = _nonempty_files(fix_report_dir, ("*.md",)) if fix_report_dir.is_dir() else []
    analysis_reports = _nonempty_files(analysis_dir, ("*.md", "*.json")) if analysis_dir.is_dir() else []

    report.counts.update(
        unit_tests=len(unit_tests),
        integration_tests=len(integration_tests),
        debug_scripts=len(debug_scripts),
        fix_reports=len(fix_reports),
        analysis_reports=len(analysis_reports),
    )

    if unit_dir.is_dir() and not unit_tests:
        report.errors.append("No non-empty unit test files were found")

    empty_test_files = sorted(
        path.relative_to(root)
        for directory in (unit_dir, integration_dir, debug_dir)
        if directory.is_dir()
        for path in directory.glob("*.py")
        if path.is_file() and path.stat().st_size == 0
    )
    if empty_test_files:
        preview = ", ".join(map(str, empty_test_files[:5]))
        suffix = f" (+{len(empty_test_files) - 5} more)" if len(empty_test_files) > 5 else ""
        report.warnings.append(f"Empty legacy test files: {preview}{suffix}")

    root_tests = sorted(path.name for path in root.glob("test_*.py") if path.is_file())
    if root_tests:
        report.errors.append(f"Test files must live under tests/: {', '.join(root_tests)}")

    root_reports = sorted(
        path.name
        for pattern in ("*_REPORT.md", "*_SUMMARY.md")
        for path in root.glob(pattern)
        if path.is_file()
    )
    if root_reports:
        report.errors.append(f"Report files must live under docs/: {', '.join(root_reports)}")

    return report


def _print_report(report: OrganizationReport) -> None:
    status = "PASS" if report.ok else "FAIL"
    print(f"[{status}] VideoTranslator organization: {report.root}")
    for name, count in report.counts.items():
        print(f"  {name}: {count}")
    for warning in report.warnings:
        print(f"  WARNING: {warning}")
    for error in report.errors:
        print(f"  ERROR: {error}")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--root",
        type=Path,
        default=PROJECT_ROOT,
        help="repository root (defaults to the parent of this script directory)",
    )
    parser.add_argument("--quiet", action="store_true", help="only communicate via the exit code")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    report = validate_organization(args.root)
    if not args.quiet:
        _print_report(report)
    return 0 if report.ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
