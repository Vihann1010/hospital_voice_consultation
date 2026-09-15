"""Every log line can be traced to its request and user, in either format."""
import json
import logging

import pytest

from app.core import logging as applog

pytestmark = pytest.mark.unit


def _record(message="saved", **extra):
    record = logging.LogRecord("app.test", logging.INFO, __file__, 1, message, None, None)
    for key, value in extra.items():
        setattr(record, key, value)
    return record


@pytest.fixture(autouse=True)
def _clear_user():
    yield
    applog.bind_user(None, None)


def test_the_request_and_user_are_attached_to_every_line():
    token = applog.bind_request("req123")
    applog.bind_user("u-1", "doctor")
    try:
        record = _record()
        applog.ContextFilter().filter(record)
        payload = json.loads(applog.JsonFormatter().format(record))
    finally:
        applog.reset_request(token)
    assert payload["request_id"] == "req123"
    assert payload["user_id"] == "u-1"
    assert payload["user_role"] == "doctor"
    assert payload["message"] == "saved"


def test_a_value_given_on_the_line_wins_over_the_context():
    token = applog.bind_request("req-context")
    try:
        record = _record(request_id="req-explicit")
        applog.ContextFilter().filter(record)
    finally:
        applog.reset_request(token)
    assert record.request_id == "req-explicit"


def test_nothing_is_attached_outside_a_request():
    record = _record()
    applog.ContextFilter().filter(record)
    assert not hasattr(record, "request_id")
    assert not hasattr(record, "user_id")


def test_pretty_format_is_one_readable_line():
    record = _record("http_error", request_id="abc", status=409, path="/api/v1/x")
    line = applog.PrettyFormatter().format(record)
    assert "http_error [req abc]" in line
    assert "status=409" in line and "path=/api/v1/x" in line
    assert "\n" not in line


def test_the_format_setting_chooses_the_formatter():
    assert isinstance(applog.build_formatter("pretty"), applog.PrettyFormatter)
    assert isinstance(applog.build_formatter("json"), applog.JsonFormatter)
    assert isinstance(applog.build_formatter("anything else"), applog.JsonFormatter)


@pytest.mark.parametrize("status_code, level", [
    (200, logging.INFO), (307, logging.INFO), (403, logging.WARNING), (422, logging.WARNING), (500, logging.ERROR),
])
def test_request_lines_are_louder_for_refusals_and_errors(status_code, level):
    assert applog.access_level(status_code) == level
