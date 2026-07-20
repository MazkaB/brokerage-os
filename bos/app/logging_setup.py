"""
Structured logging setup for BOS.

We use stdlib logging plus structlog for JSON-friendly structured output
that supports the PRD's observability requirements (section 18, "Monitoring").
"""
from __future__ import annotations

import logging
import sys

import structlog

from .config import get_settings


def configure_logging() -> None:
    settings = get_settings()
    level = getattr(logging, settings.log_level.upper(), logging.INFO)

    # Configure stdlib root
    logging.basicConfig(
        level=level,
        format="%(asctime)s %(levelname)-7s %(name)s: %(message)s",
        stream=sys.stdout,
    )

    # Quiet down noisy libs
    for noisy in ["httpx", "httpcore", "chromadb", "urllib3", "openai._base_client"]:
        logging.getLogger(noisy).setLevel(logging.WARNING)

    # Configure structlog
    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.StackInfoRenderer(),
            structlog.processors.format_exc_info,
            structlog.processors.JSONRenderer(),
        ],
        wrapper_class=structlog.make_filtering_bound_logger(level),
        context_class=dict,
        logger_factory=structlog.PrintLoggerFactory(),
        cache_logger_on_first_use=True,
    )


def get_logger(name: str = "bos"):
    return structlog.get_logger(name)
