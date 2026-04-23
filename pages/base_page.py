"""
pages/base_page.py
==================
Abstract base class for all Page Objects.
Wraps common Selenium actions with built-in waits,
retry logic, and meaningful error messages.
"""

import time
from abc import ABC
from typing import Optional

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.remote.webelement import WebElement
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import (
    TimeoutException,
    NoSuchElementException,
    StaleElementReferenceException,
    ElementClickInterceptedException,
)

from utils.logger import get_logger

log = get_logger(__name__)

# Exception types considered transient (worth retrying)
_TRANSIENT = (StaleElementReferenceException, ElementClickInterceptedException)


class BasePage(ABC):
    """
    Base Page Object.

    All page classes inherit from this and receive a
    pre-configured WebDriver instance.
    """

    def __init__(self, driver: webdriver.Chrome, timeout: int = 30):
        self.driver = driver
        self.timeout = timeout
        self.wait = WebDriverWait(driver, timeout)

    # ─────────────────────────────────────────
    # Navigation
    # ─────────────────────────────────────────

    def open(self, url: str) -> None:
        log.info(f"Navigating to: {url}")
        self.driver.get(url)
        self._wait_for_page_load()

    def _wait_for_page_load(self, timeout: int = 30) -> None:
        """Block until document.readyState == 'complete'."""
        try:
            WebDriverWait(self.driver, timeout).until(
                lambda d: d.execute_script("return document.readyState") == "complete"
            )
        except TimeoutException:
            log.warning("Page load timeout — continuing anyway.")

    # ─────────────────────────────────────────
    # Element Finders
    # ─────────────────────────────────────────

    def find(self, by: str, value: str, timeout: Optional[int] = None) -> WebElement:
        """Wait for and return a single element."""
        t = timeout or self.timeout
        try:
            return WebDriverWait(self.driver, t).until(
                EC.presence_of_element_located((by, value))
            )
        except TimeoutException:
            raise NoSuchElementException(
                f"Element not found after {t}s: [{by}] = '{value}'"
            )

    def find_visible(self, by: str, value: str, timeout: Optional[int] = None) -> WebElement:
        """Wait for an element to be visible."""
        t = timeout or self.timeout
        return WebDriverWait(self.driver, t).until(
            EC.visibility_of_element_located((by, value))
        )

    def find_all(self, by: str, value: str, timeout: Optional[int] = None) -> list[WebElement]:
        """Return a list of matching elements (may be empty)."""
        t = timeout or self.timeout
        try:
            WebDriverWait(self.driver, t).until(
                EC.presence_of_all_elements_located((by, value))
            )
        except TimeoutException:
            pass
        return self.driver.find_elements(by, value)

    def find_clickable(self, by: str, value: str, timeout: Optional[int] = None) -> WebElement:
        t = timeout or self.timeout
        return WebDriverWait(self.driver, t).until(
            EC.element_to_be_clickable((by, value))
        )

    # ─────────────────────────────────────────
    # Actions
    # ─────────────────────────────────────────

    def click(self, by: str, value: str, timeout: Optional[int] = None, retries: int = 3) -> None:
        """Click an element with retry on transient failures."""
        for attempt in range(1, retries + 1):
            try:
                el = self.find_clickable(by, value, timeout)
                self.driver.execute_script("arguments[0].scrollIntoView(true);", el)
                time.sleep(0.3)
                el.click()
                return
            except _TRANSIENT as exc:
                log.warning(f"Click attempt {attempt}/{retries} failed ({exc}), retrying…")
                time.sleep(1)
            except ElementClickInterceptedException:
                log.warning(f"Click intercepted on attempt {attempt}, using JS click…")
                el = self.find(by, value, timeout)
                self.driver.execute_script("arguments[0].click();", el)
                return
        raise RuntimeError(f"Failed to click element [{by}]='{value}' after {retries} attempts")

    def type_text(self, by: str, value: str, text: str, clear: bool = True) -> None:
        """Clear and type into an input field."""
        el = self.find_visible(by, value)
        if clear:
            el.clear()
        el.send_keys(text)

    def get_text(self, by: str, value: str, default: str = "") -> str:
        """Get element text with a fallback default."""
        try:
            return self.find(by, value).text.strip()
        except (NoSuchElementException, TimeoutException):
            return default

    def get_attribute(self, by: str, value: str, attr: str, default: str = "") -> str:
        try:
            return self.find(by, value).get_attribute(attr) or default
        except (NoSuchElementException, TimeoutException):
            return default

    def is_visible(self, by: str, value: str, timeout: int = 5) -> bool:
        try:
            WebDriverWait(self.driver, timeout).until(
                EC.visibility_of_element_located((by, value))
            )
            return True
        except TimeoutException:
            return False

    def scroll_to_bottom(self) -> None:
        self.driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")

    def switch_to_new_tab(self) -> None:
        """Switch focus to the most recently opened tab."""
        self.driver.switch_to.window(self.driver.window_handles[-1])

    def close_current_tab_and_switch_back(self) -> None:
        self.driver.close()
        self.driver.switch_to.window(self.driver.window_handles[0])

    def take_screenshot(self, path: str = "logs/screenshot.png") -> None:
        try:
            self.driver.save_screenshot(path)
            log.info(f"Screenshot saved: {path}")
        except Exception as exc:
            log.warning(f"Could not save screenshot: {exc}")

    # ─────────────────────────────────────────
    # Debug helpers
    # ─────────────────────────────────────────

    def log_form_controls(self, context: str = "", limit: int = 50) -> None:
        """
        Log a compact list of visible form controls to help debug selectors.

        Never logs element values.
        """
        from selenium.webdriver.common.by import By

        try:
            controls = self.driver.find_elements(By.CSS_SELECTOR, "input, textarea, select")
        except Exception as exc:
            log.debug(f"Could not enumerate form controls: {exc}")
            return

        if context:
            log.info(f"Form controls visible ({context}): {len(controls)} found")
        else:
            log.info(f"Form controls visible: {len(controls)} found")

        for idx, el in enumerate(controls[:limit], start=1):
            try:
                tag = (el.tag_name or "").lower()
                type_attr = (el.get_attribute("type") or "").lower()
                name = el.get_attribute("name") or ""
                el_id = el.get_attribute("id") or ""
                placeholder = el.get_attribute("placeholder") or ""
                aria = el.get_attribute("aria-label") or ""
                testid = el.get_attribute("data-testid") or el.get_attribute("data-test") or ""
                role = el.get_attribute("role") or ""
                autocomplete = el.get_attribute("autocomplete") or ""
                class_name = el.get_attribute("class") or ""

                if len(class_name) > 80:
                    class_name = class_name[:77] + "..."
                if len(placeholder) > 80:
                    placeholder = placeholder[:77] + "..."
                if len(aria) > 80:
                    aria = aria[:77] + "..."

                log.info(
                    f"[{idx:02d}] <{tag}> type='{type_attr}' name='{name}' id='{el_id}' "
                    f"placeholder='{placeholder}' aria-label='{aria}' data-testid='{testid}' "
                    f"role='{role}' autocomplete='{autocomplete}' class='{class_name}'"
                )
            except Exception as exc:
                log.debug(f"Could not describe control #{idx}: {exc}")
