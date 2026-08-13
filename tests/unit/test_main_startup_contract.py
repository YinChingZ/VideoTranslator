"""Contracts for a non-blocking, non-intrusive desktop startup."""

from __future__ import annotations

import ast
from pathlib import Path

MAIN_PATH = Path(__file__).parents[2] / "main.py"


def test_main_has_one_health_check_and_no_network_probe():
    tree = ast.parse(MAIN_PATH.read_text(encoding="utf-8"))
    function_names = {
        node.name for node in tree.body if isinstance(node, ast.FunctionDef)
    }
    imports = {
        alias.name
        for node in ast.walk(tree)
        if isinstance(node, ast.Import)
        for alias in node.names
    }

    assert "check_dependencies" not in function_names
    assert "urllib.request" not in imports


def test_optional_health_warnings_do_not_open_a_modal_at_startup():
    source = MAIN_PATH.read_text(encoding="utf-8")
    warnings_block = source[source.index("if health_report['warnings_count'] > 0:"):]

    assert "window.status_label.setText" in warnings_block
    assert "msg_box.exec()" not in warnings_block
