"""GUI log viewers must not outlive the Qt widgets they update."""

from __future__ import annotations

import logging

from app.config import AppConfig
from app.gui.processing import ProcessingWidget


def test_processing_widget_detaches_root_log_handler_on_destruction(qtbot):
    root_logger = logging.getLogger()
    before = set(root_logger.handlers)
    widget = ProcessingWidget(AppConfig())
    handler = widget._log_viewer_handler

    assert handler in root_logger.handlers
    widget.deleteLater()
    qtbot.waitUntil(lambda: handler not in root_logger.handlers, timeout=1000)
    assert set(root_logger.handlers) == before
