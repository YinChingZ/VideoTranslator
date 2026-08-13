"""The diagnostic logger must not prevent the desktop app from starting."""

from __future__ import annotations

import logging

import app.utils.logger as logger_module


def test_file_logging_failure_falls_back_to_console(monkeypatch, tmp_path):
    root = logging.getLogger()
    previous_handlers = root.handlers[:]
    previous_level = root.level

    def fail_file_handler(*_args, **_kwargs):
        raise PermissionError("state directory is read-only")

    monkeypatch.setattr(logger_module, "RotatingFileHandler", fail_file_handler)
    try:
        configured = logger_module.setup_logger(
            logging.INFO, str(tmp_path / "logs" / "application.log")
        )
        assert configured is root
        assert len(configured.handlers) == 1
        assert isinstance(configured.handlers[0], logging.StreamHandler)
        configured.error("Authorization: Bearer must-not-leak")
    finally:
        for handler in root.handlers[:]:
            root.removeHandler(handler)
            handler.close()
        root.handlers[:] = previous_handlers
        root.setLevel(previous_level)
