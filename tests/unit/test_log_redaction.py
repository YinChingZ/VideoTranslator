"""Regression tests for credentials that can appear in provider errors."""

import logging
from io import StringIO

from app.utils.logger import SensitiveInfoFilter


def _filtered_message(message, args=()):
    record = logging.LogRecord(
        "test", logging.ERROR, __file__, 1, message, args, None
    )
    SensitiveInfoFilter().filter(record)
    return record.getMessage()


def test_redacts_bearer_and_named_credentials():
    output = _filtered_message(
        "Authorization: Bearer secret-token api_key=another-secret"
    )

    assert "secret-token" not in output
    assert "another-secret" not in output
    assert output.count("***REDACTED***") == 2


def test_redacts_google_key_from_exception_url_without_hiding_other_params():
    output = _filtered_message(
        "503 for https://translation.googleapis.com/v2?key=AIza-secret&format=text"
    )

    assert "AIza-secret" not in output
    assert "format=text" in output
    assert "***REDACTED***" in output


def test_redacts_credentials_in_logging_arguments():
    output = _filtered_message(
        "request failed: %s",
        ("https://example.invalid?source=en&key=query-secret",),
    )

    assert "query-secret" not in output


def test_redacts_credentials_from_exception_traceback():
    stream = StringIO()
    handler = logging.StreamHandler(stream)
    handler.addFilter(SensitiveInfoFilter())
    handler.setFormatter(logging.Formatter("%(message)s"))
    test_logger = logging.Logger("redaction-test")
    test_logger.addHandler(handler)

    try:
        raise RuntimeError(
            "request failed: https://example.invalid/v2?key=traceback-secret&format=text"
        )
    except RuntimeError:
        test_logger.exception("provider failed")

    output = stream.getvalue()
    assert "traceback-secret" not in output
    assert "format=text" in output
    assert "***REDACTED***" in output


def test_redacts_mapping_style_logging_arguments():
    record = logging.LogRecord(
        "test",
        logging.ERROR,
        __file__,
        1,
        "request failed: %(api_key)s",
        ({"api_key": "mapping-secret"},),
        None,
    )

    SensitiveInfoFilter().filter(record)

    assert "mapping-secret" not in record.getMessage()
