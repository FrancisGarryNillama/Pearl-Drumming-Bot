"""
pages/social/base_social_page.py
=================================
Abstract base class for all social media platform page objects.
Each platform subclass implements login() and post_comment().
"""

import time
from abc import ABC, abstractmethod
from typing import Optional

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, NoSuchElementException

from utils.logger import get_logger

log = get_logger(__name__)


class BaseSocialPage(ABC):
    """
    Abstract base for all social media platform page objects.

    Subclasses must implement:
        - login(username, password) -> bool
        - post_comment(url, comment_text) -> bool
        - is_logged_in() -> bool
    """

    PLATFORM_NAME: str = "Unknown"
    LOGIN_URL: str = ""

    def __init__(self, driver: webdriver.Chrome, timeout: int = 30):
        self.driver = driver
        self.timeout = timeout
        self.wait = WebDriverWait(driver, timeout)
        self._logged_in = False

    # ─────────────────────────────────────────────────────────
    # Abstract interface
    # ─────────────────────────────────────────────────────────

    @abstractmethod
    def login(self, username: str, password: str) -> bool:
        """Authenticate with the platform. Returns True on success."""

    @abstractmethod
    def post_comment(self, url: str, comment_text: str) -> bool:
        """Navigate to url and post comment_text. Returns True on success."""

    @abstractmethod
    def is_logged_in(self) -> bool:
        """Return True if the current session is authenticated."""

    # ─────────────────────────────────────────────────────────
    # Shared helpers
    # ─────────────────────────────────────────────────────────

    def ensure_logged_in(self, username: str, password: str) -> bool:
        """Login only if not already authenticated."""
        if self._logged_in and self.is_logged_in():
            log.info(f"[{self.PLATFORM_NAME}] Already logged in.")
            return True
        log.info(f"[{self.PLATFORM_NAME}] Logging in as {username[:4]}***")
        result = self.login(username, password)
        self._logged_in = result
        return result

    def navigate(self, url: str, wait_seconds: float = 2.0) -> None:
        """Navigate to a URL and wait for page load."""
        log.info(f"[{self.PLATFORM_NAME}] Navigating to: {url}")
        self.driver.get(url)
        self._wait_for_load()
        time.sleep(wait_seconds)

    def _wait_for_load(self, timeout: int = 30) -> None:
        try:
            WebDriverWait(self.driver, timeout).until(
                lambda d: d.execute_script("return document.readyState") == "complete"
            )
        except TimeoutException:
            log.warning(f"[{self.PLATFORM_NAME}] Page load timeout — continuing.")

    def _find(self, by: str, value: str, timeout: Optional[int] = None) -> Optional[object]:
        t = timeout or self.timeout
        try:
            return WebDriverWait(self.driver, t).until(
                EC.presence_of_element_located((by, value))
            )
        except TimeoutException:
            return None

    def _find_visible(self, by: str, value: str, timeout: Optional[int] = None) -> Optional[object]:
        t = timeout or self.timeout
        try:
            return WebDriverWait(self.driver, t).until(
                EC.visibility_of_element_located((by, value))
            )
        except TimeoutException:
            return None

    def _find_clickable(self, by: str, value: str, timeout: Optional[int] = None) -> Optional[object]:
        t = timeout or self.timeout
        try:
            return WebDriverWait(self.driver, t).until(
                EC.element_to_be_clickable((by, value))
            )
        except TimeoutException:
            return None

    def _click(self, by: str, value: str, timeout: Optional[int] = None) -> bool:
        el = self._find_clickable(by, value, timeout)
        if el is None:
            return False
        try:
            self.driver.execute_script("arguments[0].scrollIntoView(true);", el)
            time.sleep(0.3)
            el.click()
            return True
        except Exception:
            try:
                self.driver.execute_script("arguments[0].click();", el)
                return True
            except Exception:
                return False

    def _type_into(self, element, text: str, slow: bool = False) -> None:
        """Type text into an element, optionally character by character."""
        element.clear()
        if slow:
            for char in text:
                element.send_keys(char)
                time.sleep(0.03)
        else:
            element.send_keys(text)

    def _type_into_contenteditable(self, element, text: str) -> None:
        """Type into a contenteditable div using JavaScript."""
        self.driver.execute_script(
            "arguments[0].focus(); arguments[0].innerText = arguments[1];",
            element, text
        )
        # Trigger input events so the UI recognises the text
        self.driver.execute_script(
            """
            var el = arguments[0];
            el.dispatchEvent(new Event('input', { bubbles: true }));
            el.dispatchEvent(new Event('change', { bubbles: true }));
            """,
            element
        )
        time.sleep(0.5)

    def _screenshot(self, name: str) -> None:
        try:
            path = f"logs/{self.PLATFORM_NAME.lower()}_{name}.png"
            self.driver.save_screenshot(path)
            log.info(f"Screenshot saved: {path}")
        except Exception:
            pass

    def _current_url(self) -> str:
        try:
            return self.driver.current_url or ""
        except Exception:
            return ""