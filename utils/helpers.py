"""
utils/helpers.py
================
General-purpose utility functions used across the project.
"""

import time
import random
import functools
import re
from datetime import datetime
from typing import Callable, Any

from thefuzz import fuzz

from utils.logger import get_logger

log = get_logger(__name__)


# ─────────────────────────────────────────────────────────────
# Retry Decorator
# ─────────────────────────────────────────────────────────────

def retry(max_attempts: int = 3, delay: float = 2.0, exceptions: tuple = (Exception,)):
    """
    Decorator that retries a function on failure.

    Args:
        max_attempts: Maximum number of attempts
        delay:        Seconds to wait between attempts
        exceptions:   Tuple of exception types to catch
    """
    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        def wrapper(*args, **kwargs) -> Any:
            last_exc: Exception | None = None
            for attempt in range(1, max_attempts + 1):
                try:
                    return func(*args, **kwargs)
                except exceptions as exc:
                    last_exc = exc
                    log.warning(
                        f"[Attempt {attempt}/{max_attempts}] "
                        f"{func.__name__} failed: {exc}"
                    )
                    if attempt < max_attempts:
                        sleep_for = delay * attempt  # exponential-ish back-off
                        log.info(f"Retrying in {sleep_for:.1f}s …")
                        time.sleep(sleep_for)
            log.error(f"{func.__name__} exhausted all {max_attempts} attempts.")
            raise last_exc  # type: ignore[misc]
        return wrapper
    return decorator


# ─────────────────────────────────────────────────────────────
# Fuzzy Keyword Detection
# ─────────────────────────────────────────────────────────────

def contains_keyword_fuzzy(
    text: str,
    keyword: str = "lifewood",
    threshold: int = 85,
) -> bool:
    """
    Return True if `text` contains a fuzzy match for `keyword`.

    Uses partial_ratio so substrings inside longer words are caught.
    Case-insensitive.
    """
    if not text:
        return False
    text_lower = text.lower()
    keyword_lower = keyword.lower()

    # Exact / contains check first (fast path)
    if keyword_lower in text_lower:
        return True

    # Fuzzy word-by-word scan
    words = re.findall(r"\w+", text_lower)
    for word in words:
        ratio = fuzz.ratio(word, keyword_lower)
        if ratio >= threshold:
            log.debug(f"Fuzzy match: '{word}' ~ '{keyword_lower}' ({ratio}%)")
            return True

    return False


# ─────────────────────────────────────────────────────────────
# Slang Opener Rotation
# ─────────────────────────────────────────────────────────────

class SlangRotator:
    """
    Tracks used slang openers and rotates through them,
    ensuring minimal repetition.
    """

    def __init__(self, openers: list[str]):
        self._openers = list(openers)
        self._used: list[str] = []

    def next(self) -> str:
        """Return the next unused slang opener, resetting when exhausted."""
        available = [o for o in self._openers if o not in self._used]
        if not available:
            self._used.clear()
            available = list(self._openers)
        choice = random.choice(available)
        self._used.append(choice)
        return choice


# ─────────────────────────────────────────────────────────────
# URL Utilities
# ─────────────────────────────────────────────────────────────

def is_quora_url(url: str) -> bool:
    """Return True if the URL belongs to Quora or is question-style."""
    if not url:
        return False
    url_lower = url.lower()
    return "quora.com" in url_lower or url_lower.endswith("?") or "/question/" in url_lower


# ─────────────────────────────────────────────────────────────
# Date Helpers
# ─────────────────────────────────────────────────────────────

def today_formatted(fmt: str = "%m/%d/%Y") -> str:
    """Return today's date in the given format."""
    return datetime.now().strftime(fmt)


def today_iso() -> str:
    return datetime.now().strftime("%Y-%m-%d")


# ─────────────────────────────────────────────────────────────
# Safe Text Extraction
# ─────────────────────────────────────────────────────────────

def safe_strip(text: str | None, default: str = "") -> str:
    """Strip whitespace from text; return default if None."""
    return (text or "").strip() or default


def truncate(text: str, max_chars: int = 3000) -> str:
    """Truncate long text for LLM context windows."""
    if len(text) <= max_chars:
        return text
    return text[:max_chars] + " … [truncated]"