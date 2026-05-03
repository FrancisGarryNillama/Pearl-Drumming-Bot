"""
pages/social/youtube_page.py
=============================
Handles YouTube login (via Google) and comment posting on videos.
"""

import time
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys

from pages.social.base_social_page import BaseSocialPage
from utils.logger import get_logger

log = get_logger(__name__)


class YouTubePage(BaseSocialPage):

    PLATFORM_NAME = "YouTube"
    LOGIN_URL = "https://accounts.google.com/ServiceLogin?service=youtube"

    _EMAIL_FIELD    = (By.CSS_SELECTOR, "input[type='email'], #identifierId")
    _EMAIL_NEXT     = (By.CSS_SELECTOR, "#identifierNext, button[jsname='LgbsSe']")
    _PASSWORD_FIELD = (By.CSS_SELECTOR, "input[type='password'], input[name='Passwd']")
    _PASSWORD_NEXT  = (By.CSS_SELECTOR, "#passwordNext, button[jsname='LgbsSe']")
    _LOGGED_IN      = (By.CSS_SELECTOR, "#avatar-btn, ytd-topbar-menu-button-renderer #avatar-btn, [aria-label='Account menu']")

    def login(self, username: str, password: str) -> bool:
        try:
            self.navigate(self.LOGIN_URL, wait_seconds=3)

            # Step 1: Enter email
            email_el = self._find_visible(*self._EMAIL_FIELD, timeout=15)
            if not email_el:
                log.error("[YouTube] Email field not found.")
                return False
            self._type_into(email_el, username)

            if not self._click(*self._EMAIL_NEXT, timeout=8):
                email_el.send_keys(Keys.RETURN)
            time.sleep(3)

            # Step 2: Enter password
            pass_el = self._find_visible(*self._PASSWORD_FIELD, timeout=15)
            if not pass_el:
                log.error("[YouTube] Password field not found.")
                return False
            self._type_into(pass_el, password)

            if not self._click(*self._PASSWORD_NEXT, timeout=8):
                pass_el.send_keys(Keys.RETURN)
            time.sleep(5)

            # Navigate to YouTube to verify
            self.navigate("https://www.youtube.com", wait_seconds=3)

            if self.is_logged_in():
                log.info("[YouTube] ✅ Login successful.")
                return True

            # Handle 2-step / recovery
            current = self._current_url()
            if "challenge" in current or "signin/v2" in current:
                log.warning("[YouTube] Google security challenge detected. Waiting 20s.")
                time.sleep(20)
                return self.is_logged_in()

            log.error("[YouTube] Login verification failed.")
            self._screenshot("login_failed")
            return False

        except Exception as exc:
            log.error(f"[YouTube] Login error: {exc}")
            self._screenshot("login_error")
            return False

    def is_logged_in(self) -> bool:
        try:
            self.navigate("https://www.youtube.com", wait_seconds=2)
            el = self._find(*self._LOGGED_IN, timeout=8)
            return el is not None
        except Exception:
            return False

    def post_comment(self, url: str, comment_text: str) -> bool:
        """Navigate to a YouTube video and post a comment."""
        try:
            self.navigate(url, wait_seconds=4)

            # Scroll to the comment section
            self.driver.execute_script("window.scrollTo(0, 800);")
            time.sleep(2)

            # Click the comment box placeholder to activate it
            placeholder_selectors = [
                (By.CSS_SELECTOR, "#simplebox-placeholder"),
                (By.XPATH, "//div[@id='simplebox-placeholder']"),
                (By.CSS_SELECTOR, "#placeholder-area"),
            ]

            for by, sel in placeholder_selectors:
                if self._click(by, sel, timeout=8):
                    time.sleep(1)
                    break

            # Find the active contenteditable comment editor
            editor_selectors = [
                "#contenteditable-root",
                "div#contenteditable-root[contenteditable='true']",
                "ytd-comment-simplebox-renderer #contenteditable-root",
                "div[contenteditable='true'][id*='content']",
            ]

            editor = None
            for sel in editor_selectors:
                editor = self._find_visible(By.CSS_SELECTOR, sel, timeout=8)
                if editor:
                    break

            if editor is None:
                log.error("[YouTube] Comment editor not found.")
                self._screenshot("editor_not_found")
                return False

            editor.click()
            time.sleep(0.3)
            editor.send_keys(comment_text)
            time.sleep(0.5)

            # Click the Submit button
            submit_selectors = [
                "#submit-button ytd-button-renderer button",
                "ytd-comment-simplebox-renderer #submit-button",
                "button[aria-label='Comment']",
                "#submit-button",
            ]
            for sel in submit_selectors:
                if self._click(By.CSS_SELECTOR, sel, timeout=5):
                    log.info("[YouTube] ✅ Comment submitted.")
                    time.sleep(2)
                    return True

            # Fallback: Ctrl+Enter
            editor.send_keys(Keys.CONTROL, Keys.RETURN)
            log.info("[YouTube] ✅ Comment submitted (Ctrl+Enter).")
            return True

        except Exception as exc:
            log.error(f"[YouTube] post_comment error: {exc}")
            self._screenshot("post_error")
            return False
