"""Guardrails that prevent historical false-positive tests from re-entering CI."""

from __future__ import annotations

import ast
from pathlib import Path

from tests.conftest import LEGACY_TEST_MODULES

UNIT_DIR = Path(__file__).parent


class _DirectReturnVisitor(ast.NodeVisitor):
    """Find returns in one test without descending into helper functions."""

    def __init__(self) -> None:
        self.returns: list[ast.Return] = []

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        del node

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
        del node

    def visit_Return(self, node: ast.Return) -> None:
        self.returns.append(node)


def _direct_returns(test: ast.FunctionDef | ast.AsyncFunctionDef) -> list[ast.Return]:
    visitor = _DirectReturnVisitor()
    for statement in test.body:
        visitor.visit(statement)
    return visitor.returns


def test_default_suite_has_no_value_returning_test_functions() -> None:
    """Pytest ignores return values, so tests must assert or raise on failure."""

    offenders: list[str] = []
    for path in sorted(UNIT_DIR.glob("test_*.py")):
        if path.name in LEGACY_TEST_MODULES:
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            if not node.name.startswith("test_"):
                continue
            for returned in _direct_returns(node):
                if returned.value is not None:
                    offenders.append(f"{path.name}:{returned.lineno} ({node.name})")

    assert offenders == [], "Tests return values instead of failing:\n" + "\n".join(offenders)


def test_default_suite_does_not_replace_imports_in_sys_modules() -> None:
    """Module-level dependency mocks make collection order-dependent."""

    offenders: list[str] = []
    for path in sorted(UNIT_DIR.glob("test_*.py")):
        if path.name in LEGACY_TEST_MODULES:
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if not isinstance(node, (ast.Assign, ast.AnnAssign)):
                continue
            targets = node.targets if isinstance(node, ast.Assign) else [node.target]
            for target in targets:
                if not isinstance(target, ast.Subscript):
                    continue
                value = target.value
                if (
                    isinstance(value, ast.Attribute)
                    and isinstance(value.value, ast.Name)
                    and value.value.id == "sys"
                    and value.attr == "modules"
                ):
                    offenders.append(f"{path.name}:{node.lineno}")

    assert offenders == [], "Default tests mutate sys.modules at import time:\n" + "\n".join(
        offenders
    )
