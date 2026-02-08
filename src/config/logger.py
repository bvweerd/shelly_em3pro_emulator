"""Logging configuration module."""

import logging
import sys
from typing import Optional

import structlog

_configured = False


def setup_logging(level: str = "INFO", log_format: Optional[str] = None) -> None:
    """Set up logging configuration.

    Args:
        level: Log level (DEBUG, INFO, WARNING, ERROR).
        log_format: Optional format string for standard logging.
    """
    global _configured

    if _configured:
        return

    # Convert level string to logging constant
    numeric_level = getattr(logging, level.upper(), logging.INFO)

    # Configure standard logging
    if log_format:
        logging.basicConfig(
            level=numeric_level,
            format=log_format,
            stream=sys.stdout,
        )
    else:
        logging.basicConfig(
            level=numeric_level,
            stream=sys.stdout,
        )

    # Configure structlog
    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.StackInfoRenderer(),
            structlog.dev.set_exc_info,
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.dev.ConsoleRenderer(colors=True),
        ],
        wrapper_class=structlog.make_filtering_bound_logger(numeric_level),
        context_class=dict,
        logger_factory=structlog.PrintLoggerFactory(),
        cache_logger_on_first_use=True,
    )

    _configured = True


def get_logger(name: str) -> structlog.BoundLogger:
    """Get a logger instance.

    Args:
        name: Logger name (typically __name__).

    Returns:
        Configured structlog logger.
    """
    return structlog.get_logger(name)
