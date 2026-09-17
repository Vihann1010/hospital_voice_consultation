"""Structured logging, with the request and the user attached to every line.

One JSON object per line by default, so logs ship straight into Loki /
CloudWatch / ELK without a parsing layer. `LOG_FORMAT=pretty` prints the same
information as readable single lines for local debugging.

Every line logged while a request is being handled carries its `request_id`
and, once the caller is signed in, `user_id` and `user_role`. The request id is
returned to the browser in every error response, so a failure a member of staff
reports can be traced to every line that request produced:

    docker logs satya-backend 2>&1 | grep <request_id>

Log identifiers and outcomes, never request bodies or clinical content.
"""
import contextvars
import json
import logging
import sys
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from app.core.config import settings

_RESERVED = {
    "name", "msg", "args", "levelname", "levelno", "pathname", "filename",
    "module", "exc_info", "exc_text", "stack_info", "lineno", "funcName",
    "created", "msecs", "relativeCreated", "thread", "threadName",
    "processName", "process", "taskName", "message",
}

_request_id: contextvars.ContextVar[Optional[str]] = contextvars.ContextVar("request_id", default=None)
_user_id: contextvars.ContextVar[Optional[str]] = contextvars.ContextVar("user_id", default=None)
_user_role: contextvars.ContextVar[Optional[str]] = contextvars.ContextVar("user_role", default=None)
_CONTEXT = (("request_id", _request_id), ("user_id", _user_id), ("user_role", _user_role))


# ------------------------------------------------------------------ context
def bind_request(request_id: Optional[str]) -> contextvars.Token:
    """Attach a request id to everything logged from here on in this request."""
    return _request_id.set(request_id)


def reset_request(token: contextvars.Token) -> None:
    _request_id.reset(token)


def bind_user(user_id: Any, role: Optional[str]) -> None:
    """Attach the signed-in user; called once authentication succeeds."""
    _user_id.set(str(user_id) if user_id else None)
    _user_role.set(role)


def current_request_id() -> Optional[str]:
    return _request_id.get()


class ContextFilter(logging.Filter):
    """Adds request_id, user_id and user_role to a record that does not already carry them."""

    def filter(self, record: logging.LogRecord) -> bool:
        for name, variable in _CONTEXT:
            if getattr(record, name, None) is None:
                value = variable.get()
                if value is not None:
                    setattr(record, name, value)
        return True


# --------------------------------------------------------------- formatters
def _extras(record: logging.LogRecord) -> Dict[str, Any]:
    return {key: value for key, value in record.__dict__.items()
            if key not in _RESERVED and not key.startswith("_")}


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload: Dict[str, Any] = {
            "ts": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            **_extras(record),
        }
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        return json.dumps(payload, ensure_ascii=False, default=str)


class PrettyFormatter(logging.Formatter):
    """`14:02:11 WARNING app.api: http_error [req 1a2b] status=409 path=/api/v1/...`"""

    def format(self, record: logging.LogRecord) -> str:
        extras = _extras(record)
        request_id = extras.pop("request_id", None)
        line = f"{datetime.now():%H:%M:%S} {record.levelname:<7} {record.name}: {record.getMessage()}"
        if request_id:
            line += f" [req {request_id}]"
        if extras:
            line += " " + " ".join(f"{key}={value}" for key, value in extras.items())
        if record.exc_info:
            line += "\n" + self.formatException(record.exc_info)
        return line


def build_formatter(log_format: str) -> logging.Formatter:
    return PrettyFormatter() if (log_format or "").lower() == "pretty" else JsonFormatter()


def access_level(status_code: int) -> int:
    """How loudly to log a finished request: errors loud, refusals noticeable, the rest quiet."""
    if status_code >= 500:
        return logging.ERROR
    if status_code >= 400:
        return logging.WARNING
    return logging.INFO


# ------------------------------------------------------------------- set-up
def configure_logging() -> None:
    root = logging.getLogger()
    root.handlers.clear()
    handler = logging.StreamHandler(sys.stdout)
    handler.addFilter(ContextFilter())
    handler.setFormatter(build_formatter(settings.LOG_FORMAT))
    root.addHandler(handler)
    root.setLevel(settings.LOG_LEVEL)
    # Our own request log replaces uvicorn's access log, which knows no request id or user.
    for noisy in ("uvicorn.access", "websockets.client", "httpx", "httpcore"):
        logging.getLogger(noisy).setLevel(logging.WARNING)


def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(name)
