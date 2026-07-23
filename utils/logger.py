"""
Centralized logging configuration.

Every module should obtain its logger by calling
`get_logger(__name__)`.
"""

from __future__ import annotations

import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path

from config import get_settings

_LOGGER_INITIALIZED = False


def _configure_root_logger() -> None:
    """
    Configure the application's root logger.

    This function is executed only once.
    """
    global _LOGGER_INITIALIZED

    if _LOGGER_INITIALIZED:
        return

    settings = get_settings()

    log_directory = Path("logs")
    log_directory.mkdir(parents=True, exist_ok=True)

    formatter = logging.Formatter(
        fmt="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)

    file_handler = RotatingFileHandler(
        filename=log_directory / "application.log",
        maxBytes=5 * 1024 * 1024,
        backupCount=5,
        encoding="utf-8",
    )
    file_handler.setFormatter(formatter)

    root_logger = logging.getLogger()

    root_logger.setLevel(settings.log_level.upper())

    if not root_logger.handlers:
        root_logger.addHandler(console_handler)
        root_logger.addHandler(file_handler)

    _LOGGER_INITIALIZED = True


def get_logger(name: str) -> logging.Logger:
    """
    Return a configured logger.

    Args:
        name: Logger name.

    Returns:
        Configured logger instance.
    """
    _configure_root_logger()
    return logging.getLogger(name)