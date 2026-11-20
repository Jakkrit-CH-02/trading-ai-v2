"""Structured JSON logging with secret redaction."""

import logging
from collections.abc import MutableMapping
from typing import Any

import structlog

_SENSITIVE = ("key", "secret", "signature", "password", "token", "totp")


def redact(_: Any, __: str, event_dict: MutableMapping[str, Any]) -> MutableMapping[str, Any]:
    for k in list(event_dict):
        if any(s in k.lower() for s in _SENSITIVE):
            event_dict[k] = "***"
    return event_dict


def configure_logging(service: str) -> None:
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    # httpx logs full URLs at INFO; signed GET requests carry `signature=` in the query string
    for noisy in ("httpx", "httpcore"):
        logging.getLogger(noisy).setLevel(logging.WARNING)
    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso", utc=True),
            redact,
            structlog.processors.JSONRenderer(),
        ],
        wrapper_class=structlog.make_filtering_bound_logger(logging.INFO),
    )
    structlog.contextvars.bind_contextvars(service=service)
