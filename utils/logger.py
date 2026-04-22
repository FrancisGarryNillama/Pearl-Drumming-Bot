"""
utils/logger.py
===============
Centralised logger with color output for console
and rotating file handler. All modules import from here.
"""

import logging
import os
import sys
from logging.handlers import RotatingFileHandler
from pathlib import Path

try:
    import colorlog
    _HAS_COLORLOG = True
except ImportError:
    _HAS_COLORLOG = False


def get_logger(name: str = "pearl27", level: str = "INFO", log_file: str = "logs/automation.log") -> logging.Logger:
    """
    Build and return a named logger.

    Args:
        name:     Logger name (usually module __name__)
        level:    Logging level string e.g. 'INFO', 'DEBUG'
        log_file: Path for rotating log file

    Returns:
        Configured logging.Logger instance
    """
    logger = logging.getLogger(name)

    # Avoid adding handlers multiple times
    if logger.handlers:
        return logger

    logger.setLevel(getattr(logging, level.upper(), logging.INFO))

    # ── Console Handler ──────────────────────────────────────
    if _HAS_COLORLOG:
        console_fmt = colorlog.ColoredFormatter(
            "%(log_color)s%(asctime)s [%(levelname)-8s] %(name)s — %(message)s%(reset)s",
            datefmt="%H:%M:%S",
            log_colors={
                "DEBUG":    "cyan",
                "INFO":     "green",
                "WARNING":  "yellow",
                "ERROR":    "red",
                "CRITICAL": "bold_red",
            },
        )
    else:
        console_fmt = logging.Formatter(
            "%(asctime)s [%(levelname)-8s] %(name)s — %(message)s",
            datefmt="%H:%M:%S",
        )

    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(console_fmt)
    logger.addHandler(console_handler)

    # ── File Handler ─────────────────────────────────────────
    log_path = Path(log_file)
    log_path.parent.mkdir(parents=True, exist_ok=True)

    file_fmt = logging.Formatter(
        "%(asctime)s [%(levelname)-8s] %(name)s — %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    file_handler = RotatingFileHandler(
        log_path,
        maxBytes=5 * 1024 * 1024,   # 5 MB
        backupCount=3,
        encoding="utf-8",
    )
    file_handler.setFormatter(file_fmt)
    logger.addHandler(file_handler)

    return logger


# ── Convenience singleton (optional direct import) ──────────
_root_logger: logging.Logger | None = None


def setup_root_logger(level: str = "INFO", log_file: str = "logs/automation.log") -> logging.Logger:
    global _root_logger
    _root_logger = get_logger("pearl27", level, log_file)
    return _root_logger


def mask(value: str, visible: int = 4) -> str:
    """Mask a sensitive string, showing only the last `visible` chars."""
    if not value or len(value) <= visible:
        return "***"
    return f"***{value[-visible:]}"