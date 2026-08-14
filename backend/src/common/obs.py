"""Structured JSON logging with the Lambda request id attached to every line.

CloudWatch Logs Insights can query these directly, e.g.
  fields @timestamp, event, stage, ms | filter event = "fallback_used"
"""
import json
import logging
import os
import sys
import time
from contextlib import contextmanager

_LEVEL = os.environ.get("LOG_LEVEL", "INFO").upper()

_logger = logging.getLogger("meme-alchemist")
if not _logger.handlers:
    _handler = logging.StreamHandler(sys.stdout)
    _handler.setFormatter(logging.Formatter("%(message)s"))
    _logger.addHandler(_handler)
_logger.setLevel(_LEVEL)
_logger.propagate = False

# Set once per invocation by bind_request().
_request_id = "-"


def bind_request(context) -> str:
    """Attach the Lambda request id to all subsequent log lines."""
    global _request_id
    _request_id = getattr(context, "aws_request_id", "-") or "-"
    return _request_id


def current_request_id() -> str:
    return _request_id


def log(event: str, level: int = logging.INFO, **fields) -> None:
    payload = {"event": event, "requestId": _request_id}
    payload.update(fields)
    try:
        line = json.dumps(payload, default=str)
    except (TypeError, ValueError):
        line = json.dumps({"event": event, "requestId": _request_id, "unserializable": True})
    _logger.log(level, line)


def warn(event: str, **fields) -> None:
    log(event, level=logging.WARNING, **fields)


def error(event: str, **fields) -> None:
    log(event, level=logging.ERROR, **fields)


@contextmanager
def stage(name: str, **fields):
    """Time a pipeline stage and emit stage_ok / stage_failed with duration."""
    started = time.time()
    try:
        yield
    except Exception as exc:
        error(
            "stage_failed",
            stage=name,
            ms=round((time.time() - started) * 1000),
            errorType=type(exc).__name__,
            error=str(exc)[:500],
            **fields,
        )
        raise
    else:
        log("stage_ok", stage=name, ms=round((time.time() - started) * 1000), **fields)
