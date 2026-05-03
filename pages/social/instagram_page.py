"""
pages/social/instagram_page.py
================================
Handles Instagram login and comment posting on posts.
Instagram web has limitations — works best on individual post URLs
(e.g. https://www.instagram.com/p/XXXX/).
"""

import time
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys

from pages.social.base_social_page import BaseSocialPage
from utils.logger import get_logger

log = get_logger(__name__)


class InstagramPage(BaseSocialPage):

    PLATFORM_NAME = "Instagram"
    LOGIN_URL = "https://www.instagram.com/accounts/login/"

    _USERNAME  = (By.CSS_SELECTOR, "input[name='username'], input[aria-label='Phone number, username, or email']")
    _PASSWORD  = (By.CSS_SELECTOR, "input[name='password'], input[aria-label='Password']")
    _SUBMIT    = (By.CSS_SELECTOR, "button[type='submit'], .L3NKy, div[role='button'][tabindex='0']")
    _LOGGED_IN = (By.CSS_SELECTOR, "a[href*='/direct/inbox/'], svg[aria-label='Direct'], [aria-label='Home']")

    def login(self, username: str, password: str) -> bool:
        try:
            self.navigate(self.LOGIN_URL, wait_seconds=3)

            # Dismiss cookie banner if shown
            self._dismiss_cookie_dialog()

            user_el = self._find_visible(*self._USERNAME, timeout=15)
            if not user_el:
                log.error("[Instagram] Username field not found.")
                return False
            self._type_into(user_el, username)

            pass_el = self._find_visible(*self._PASSWORD, timeout=10)
            if not pass_el:
                log.error("[Instagram] Password field not found.")
                return False
            self._type_into(pass_el, password)

            if not self._click(*self._SUBMIT, timeout=8):
                pass_el.send_keys(Keys.RETURN)

            time.sleep(5)

            # Dismiss "Save your login info?" popup
            self._dismiss_save_login_popup()
            # Dismiss "Turn on notifications?" popup
            self._dismiss_notifications_popup()

            if self.is_logged_in():
                log.info("[Instagram] ✅ Login successful.")
                return True

            # 2FA or challenge
            current = self._current_url()
            if "challenge" in current or "two_factor" in current:
                log.warning("[Instagram] Security challenge detected. Waiting 20s.")
                time.sleep(20)
                return self.is_logged_in()

            log.error("[Instagram] Login verification failed.")
            self._screenshot("login_failed")
            return False

        except Exception as exc:
            log.error(f"[Instagram] Login error: {exc}")
            self._screenshot("login_error")
            return False

    def _dismiss_cookie_dialog(self) -> None:
        xpaths = [
            "//button[contains(normalize-space(.),'Accept all')]",
            "//button[contains(normalize-space(.),'Allow all')]",
            "//button[contains(normalize-space(.),'Allow essential')]",
        ]
        for xp in xpaths:
            if self._click(By.XPATH, xp, timeout=3):
                time.sleep(0.5)
                return

    def _dismiss_save_login_popup(self) -> None:
        xpaths = [
            "//button[contains(normalize-space(.),'Not now')]",
            "//button[contains(normalize-space(.),'Not Now')]",
        ]
        for xp in xpaths:
            if self._click(By.XPATH, xp, timeout=5):
                time.sleep(0.5)
                return

    def _dismiss_notifications_popup(self) -> None:
        xpaths = [
            "//button[contains(normalize-space(.),'Not Now')]",
            "//button[contains(normalize-space(.),'Not now')]",
        ]
        for xp in xpaths:
            if self._click(By.XPATH, xp, timeout=5):
                time.sleep(0.5)
                return

    def is_logged_in(self) -> bool:
        try:
            url = self._current_url()
            if "login" in url or "accounts" in url:
                return False
            el = self._find(*self._LOGGED_IN, timeout=5)
            return el is not None
        except Exception:
            return False

    def post_comment(self, url: str, comment_text: str) -> bool:
        """Navigate to an Instagram post and add a comment."""
        try:
            self.navigate(url, wait_seconds=4)
            self._dismiss_cookie_dialog()

            # Find the comment input area
            comment_selectors = [
                "textarea[aria-label='Add a comment…']",
                "textarea[placeholder='Add a comment…']",
                "textarea[aria-label*='comment']",
                "textarea[placeholder*='comment']",
                "textarea",
            ]

            comment_box = None
            for sel in comment_selectors:
                el = self._find_visible(By.CSS_SELECTOR, sel, timeout=8)
                if el:
                    comment_box = el
                    break

            if comment_box is None:
                log.error("[Instagram] Comment textarea not found.")
                self._screenshot("comment_not_found")
                return False

            comment_box.click()
            time.sleep(0.5)
            comment_box.send_keys(comment_text)
            time.sleep(0.5)

            # Try posting via submit button
            submit_xpaths = [
                "//button[contains(normalize-space(.),'Post')]",
                "//div[@role='button'][contains(normalize-space(.),'Post')]",
            ]
            for xp in submit_xpaths:
                if self._click(By.XPATH, xp, timeout=5):
                    log.info("[Instagram] ✅ Comment submitted.")
                    time.sleep(2)
                    return True

            # Fallback: Enter
            comment_box.send_keys(Keys.RETURN)
            log.info("[Instagram] ✅ Comment submitted (Enter).")
            time.sleep(2)
            return True

        except Exception as exc:
            log.error(f"[Instagram] post_comment error: {exc}")
            self._screenshot("post_error")
            return False
