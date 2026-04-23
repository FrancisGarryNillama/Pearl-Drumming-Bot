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
    _INVITATION_FIELD_CSS = (
        "input[name='invitation_code'], input[name='invite_code'], input[name='invitation'], input[name='invite'], "
        "input[id*='invite'], input[id*='invitation'], input[name*='invite'], input[name*='invitation'], "
        "input[placeholder*='Invitation'], input[placeholder*='Invite'], input[aria-label*='Invitation'], input[aria-label*='Invite'], "
        "[data-testid*='invite'] input, input[data-testid*='invite'], [data-testid*='invitation'] input, input[data-testid*='invitation']"
    )
    _INVITATION_FIELD_XPATHS = [
        # By placeholder / aria-label / id / name (case-insensitive)
        "//input[contains(translate(@placeholder,'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'invitation') or "
        "contains(translate(@placeholder,'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'invite') or "
        "contains(translate(@aria-label,'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'invitation') or "
        "contains(translate(@aria-label,'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'invite') or "
        "contains(translate(@name,'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'invitation') or "
        "contains(translate(@name,'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'invite') or "
        "contains(translate(@id,'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'invitation') or "
        "contains(translate(@id,'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'invite')]",
        # By nearby label text
        "//label[contains(translate(normalize-space(.),'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'invitation') or "
        "contains(translate(normalize-space(.),'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'invite')]/following::input[1]",
        # By data-testid (common in React apps)
        "//*[@data-testid][contains(translate(@data-testid,'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'invite') or "
        "contains(translate(@data-testid,'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'invitation')]//input[1]",
    ]
    _SUBMIT_BUTTON  = (By.CSS_SELECTOR, "button[type='submit'], input[type='submit'], button.login-btn, button.sign-in")
    _DASHBOARD_INDICATOR = (By.XPATH, "//*[contains(text(),'Dashboard') or contains(text(),'Welcome') or contains(@class,'dashboard') or contains(@href,'dashboard')]")
    _ERROR_MESSAGE  = (By.XPATH, "//*[contains(@class,'error') or contains(@class,'alert') or contains(text(),'Invalid')]")

    def login(self, url: str, username: str, password: str, invitation_code: str = "") -> bool:
        """
        Full login sequence.

        Args:
            url:             Platform base URL
            username:        User email / username
            password:        Account password
            invitation_code: Optional invitation code

        Returns:
            True if login succeeded, False otherwise.
        """
        log.info(f"Opening login page: {url}")
        self.open(url)

        # Some SPAs need a moment to hydrate
        import time
        time.sleep(2)

        # If a previous session is still valid, we may already be on the dashboard.
        current_url = self.driver.current_url or ""
        if "dashboard" in current_url.lower() or self.is_visible(*self._DASHBOARD_INDICATOR, timeout=3):
            log.info(f"✅ Already logged in (URL: {current_url})")
            return True

        log.info(f"Entering credentials for: {username[:4]}***")
        self._enter_username(username)
        self._enter_password(password)
        if invitation_code:
            self._enter_invitation_code(invitation_code)
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
                el = self.find_visible(by, sel, timeout=8)
                el.clear()
                el.send_keys(username)
                self._last_username_el = el
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
                el = self.find_visible(by, sel, timeout=8)
                el.clear()
                el.send_keys(password)
                self._last_password_el = el
                log.debug("Password entered.")
                return
            except Exception:
                continue
        raise NoSuchElementException("Could not locate password input field.")

    def _enter_invitation_code(self, invitation_code: str) -> None:
        """Locate the invitation code field and type the value."""
        # 1) Try direct CSS candidates
        for sel in self._INVITATION_FIELD_CSS.split(","):
            sel = sel.strip()
            if not sel:
                continue
            try:
                self.type_text(By.CSS_SELECTOR, sel, invitation_code)
                log.debug(f"Invitation code entered via CSS selector: {sel}")
                return
            except Exception:
                continue

        # 2) Try robust XPath fallbacks
        for xp in self._INVITATION_FIELD_XPATHS:
            try:
                self.type_text(By.XPATH, xp, invitation_code)
                log.debug(f"Invitation code entered via XPath: {xp}")
                return
            except Exception:
                continue

        # 3) Field might be hidden behind a toggle; try revealing it then retry once
        if self._try_reveal_invitation_code_field():
            for sel in self._INVITATION_FIELD_CSS.split(","):
                sel = sel.strip()
                if not sel:
                    continue
                try:
                    self.type_text(By.CSS_SELECTOR, sel, invitation_code)
                    log.debug(f"Invitation code entered after reveal via CSS selector: {sel}")
                    return
                except Exception:
                    continue
            for xp in self._INVITATION_FIELD_XPATHS:
                try:
                    self.type_text(By.XPATH, xp, invitation_code)
                    log.debug(f"Invitation code entered after reveal via XPath: {xp}")
                    return
                except Exception:
                    continue

        log.warning("Could not locate invitation code input field. Continuing without it.")
        self.log_form_controls(context="after invitation code lookup")

    def _try_reveal_invitation_code_field(self) -> bool:
        """
        Some login flows hide the invitation code input behind a link/button.
        Attempt to click common toggles. Returns True if any click happened.
        """
        candidates = [
            (By.XPATH,
             "//button[contains(translate(normalize-space(.),'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'invitation') or "
             "contains(translate(normalize-space(.),'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'invite')]"),
            (By.XPATH,
             "//a[contains(translate(normalize-space(.),'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'invitation') or "
             "contains(translate(normalize-space(.),'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'invite')]"),
        ]

        for by, value in candidates:
            try:
                els = self.find_all(by, value, timeout=2)
            except Exception:
                els = []

            for el in els[:3]:
                try:
                    self.driver.execute_script("arguments[0].scrollIntoView(true);", el)
                    self.driver.execute_script("arguments[0].click();", el)
                    log.info("Clicked an invitation-code toggle to reveal the field.")
                    import time
                    time.sleep(0.8)
                    return True
                except Exception:
                    continue
        return False

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
        try:
            el = getattr(self, "_last_password_el", None)
            if el is not None:
                el.send_keys(Keys.RETURN)
                return
        except Exception:
            pass

        try:
            self.driver.switch_to.active_element.send_keys(Keys.RETURN)
        except Exception:
            # Final fallback: try the configured password selectors again, quickly.
            p_by, p_selector = self._PASSWORD_FIELD
            for p_sel in p_selector.split(","):
                p_sel = p_sel.strip()
                try:
                    self.find_visible(p_by, p_sel, timeout=3).send_keys(Keys.RETURN)
                    return
                except Exception:
                    continue
            raise

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
