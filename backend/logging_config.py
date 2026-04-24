"""
Structured logging for the backend.

Per-request context (campaign_id, request_id) is carried via contextvars and
stitched into every log record by a logging.Filter, so any module that just
does `log = logging.getLogger(__name__); log.info(...)` gets the tags for free.
"""

from __future__ import annotations

import contextvars
import logging
import sys

campaign_id_ctx: contextvars.ContextVar[str] = contextvars.ContextVar("campaign_id", default="-")
request_id_ctx: contextvars.ContextVar[str] = contextvars.ContextVar("request_id", default="-")


class ContextFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        record.campaign_id = campaign_id_ctx.get()
        record.request_id = request_id_ctx.get()
        return True


_FORMAT = (
    "%(asctime)s %(levelname)-5s [%(name)s] "
    "[campaign=%(campaign_id)s req=%(request_id)s] %(message)s"
)


def configure_logging(level: int = logging.INFO) -> None:
    root = logging.getLogger()
    if getattr(root, "_tt_configured", False):
        return

    handler = logging.StreamHandler(stream=sys.stdout)
    handler.setFormatter(logging.Formatter(_FORMAT, datefmt="%H:%M:%S"))
    handler.addFilter(ContextFilter())

    root.handlers.clear()
    root.addHandler(handler)
    root.setLevel(level)

    # Quiet down noisy third-party loggers.
    for name in ("httpx", "httpcore", "chromadb.telemetry"):
        logging.getLogger(name).setLevel(logging.WARNING)

    root._tt_configured = True  # type: ignore[attr-defined]
