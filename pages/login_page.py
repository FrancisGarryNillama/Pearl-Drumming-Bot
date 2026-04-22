"""
pages/login_page.py
===================
Page Object for the Pearl27 login flow.
Handles navigation, credential entry, and login validation.
"""

from selenium.webdriver.common.by import By
from selenium.common.exceptions import NoSuchElementException, TimeoutException

from pages.base_page import BasePage
from utils.logger import get_logger, mask

log = get_logger(__name__)


class LoginPage(BasePage):
    """Encapsulates all interactions on the login / auth screen."""

    # ── Locators ────────────────────────────────────────────
    # Update these selectors to match the actual Pearl27 HTML.
    # Using flexible XPath fallbacks for robustness.

    _USERNAME_FIELD = (By.CSS_SELECTOR, "input[type='email'], input[name='email'], input[name='username'], #email, #username")
    _PASSWORD_FIELD = (By.CSS_SELECTOR, "input[type='password'], input[name='password'], #password")
    _SUBMIT_BUTTON  = (By.CSS_SELECTOR, "button[type='submit'], input[type='submit'], button.login-btn, button.sign-in")
    _DASHBOARD_INDICATOR = (By.XPATH, "//*[contains(text(),'Dashboard') or contains(text(),'Welcome') or contains(@class,'dashboard') or contains(@href,'dashboard')]")
    _ERROR_MESSAGE  = (By.XPATH, "//*[contains(@class,'error') or contains(@class,'alert') or contains(text(),'Invalid')]")

    def login(self, url: str, username: str, password: str) -> bool:
        """
        Full login sequence.

        Args:
            url:      Platform base URL
            username: User email / username
            password: Account password

        Returns:
            True if login succeeded, False otherwise.
        """
        log.info(f"Opening login page: {url}")
        self.open(url)

        # Some SPAs need a moment to hydrate
        import time
        time.sleep(2)

        log.info(f"Entering credentials for: {username[:4]}***")
        self._enter_username(username)
        self._enter_password(password)
        self._submit()

        return self._verify_login()

    # ─────────────────────────────────────────────────────────
    # Private helpers
    # ─────────────────────────────────────────────────────────

    def _enter_username(self, username: str) -> None:
        """Locate the username/email field and type the value."""
        by, selector = self._USERNAME_FIELD
        for sel in selector.split(","):
            sel = sel.strip()
            try:
                self.type_text(by, sel, username)
                log.debug(f"Username entered via selector: {sel}")
                return
            except Exception:
                continue
        raise NoSuchElementException("Could not locate username input field.")

    def _enter_password(self, password: str) -> None:
        by, selector = self._PASSWORD_FIELD
        for sel in selector.split(","):
            sel = sel.strip()
            try:
                self.type_text(by, sel, password)
                log.debug("Password entered.")
                return
            except Exception:
                continue
        raise NoSuchElementException("Could not locate password input field.")

    def _submit(self) -> None:
        by, selector = self._SUBMIT_BUTTON
        for sel in selector.split(","):
            sel = sel.strip()
            try:
                self.click(by, sel, timeout=10)
                log.info("Login form submitted.")
                return
            except Exception:
                continue
        # Last resort — press Enter on the password field
        log.warning("Submit button not found, pressing Enter on password field.")
        from selenium.webdriver.common.keys import Keys
        self.find(By.CSS_SELECTOR, "input[type='password']").send_keys(Keys.RETURN)

    def _verify_login(self, timeout: int = 15) -> bool:
        """
        Confirm successful login by checking for dashboard indicator
        or absence of login-specific elements.
        """
        import time
        time.sleep(2)  # Allow redirect

        # Check for error message first
        if self.is_visible(*self._ERROR_MESSAGE, timeout=3):
            error_text = self.get_text(*self._ERROR_MESSAGE)
            log.error(f"Login failed. Error message: {error_text}")
            return False

        # Check for dashboard elements
        if self.is_visible(*self._DASHBOARD_INDICATOR, timeout=timeout):
            log.info("✅ Login successful — dashboard detected.")
            return True

        # Fallback: check URL changed from login
        current_url = self.driver.current_url
        if "login" not in current_url.lower() and "signin" not in current_url.lower():
            log.info(f"✅ Login appears successful (URL: {current_url})")
            return True

        log.error("❌ Login verification failed — still on login page.")
        self.take_screenshot("logs/login_failure.png")
        return False