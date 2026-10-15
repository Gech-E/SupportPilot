"""Structured JSON logging.

Rules (see CLAUDE.md): log ids and outcomes, never passwords, tokens, or message bodies.
Request-scoped fields such as ``request_id`` are bound through contextvars by the middleware.
"""

import logging
import sys

import structlog


def configure_logging(level: str = "INFO") -> None:
    level_number = logging.getLevelNamesMapping()[level.upper()]
    logging.basicConfig(format="%(message)s", stream=sys.stdout, level=level_number)
    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso", utc=True),
            structlog.processors.format_exc_info,
            structlog.processors.JSONRenderer(),
        ],
        wrapper_class=structlog.make_filtering_bound_logger(level_number),
        logger_factory=structlog.PrintLoggerFactory(),
        cache_logger_on_first_use=True,
    )
