"""Logging setup for tomato-vine — chat and error logs."""

from __future__ import annotations

import logging
import os
from pathlib import Path

BASE_DIR = Path(os.environ.get("TV_HOME", Path.home() / ".config" / "tomato-vine"))
CHAT_LOG = Path(os.environ.get("TV_CHAT_LOG", BASE_DIR / "chat.log"))
ERROR_LOG = Path(os.environ.get("TV_ERROR_LOG", BASE_DIR / "error.log"))

_chat_logger: logging.Logger | None = None
_error_logger: logging.Logger | None = None


def setup_logging(
    debug: bool = False,
    log_chat: bool = False,
    log_errors: bool = False,
) -> None:
    """Initialize chat and error loggers."""
    global _chat_logger, _error_logger

    BASE_DIR.mkdir(parents=True, exist_ok=True)

    _chat_logger = logging.getLogger("tv.chat")
    _chat_logger.setLevel(logging.DEBUG)
    _chat_logger.propagate = False
    _chat_logger.handlers.clear()
    if log_chat:
        chat_handler = logging.FileHandler(CHAT_LOG, mode="a", encoding="utf-8")
        chat_handler.setFormatter(logging.Formatter("%(asctime)s %(message)s", datefmt="%H:%M:%S"))
        _chat_logger.addHandler(chat_handler)

    _error_logger = logging.getLogger("tv.error")
    _error_logger.setLevel(logging.DEBUG if debug else logging.INFO)
    _error_logger.propagate = False
    _error_logger.handlers.clear()
    if log_errors or debug:
        error_handler = logging.FileHandler(ERROR_LOG, mode="a", encoding="utf-8")
        error_handler.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(message)s", datefmt="%Y-%m-%d %H:%M:%S"))
        _error_logger.addHandler(error_handler)

    for name in ("tv.irc.connection", "tv.irc.capabilities", "tv.tui.app"):
        logger = logging.getLogger(name)
        logger.setLevel(logging.DEBUG if debug else logging.INFO)
        logger.handlers.clear()
        if log_errors or debug:
            logger.addHandler(error_handler)


def chat_log() -> logging.Logger:
    """Return the chat logger."""
    global _chat_logger
    if _chat_logger is None:
        setup_logging()
    return _chat_logger


def error_log() -> logging.Logger:
    """Return the error/connection logger."""
    global _error_logger
    if _error_logger is None:
        setup_logging()
    return _error_logger
