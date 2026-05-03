"""
pages/social/facebook_page.py
==============================
Handles Facebook login and comment posting.
Note: Facebook has aggressive bot detection — runs non-headless only.
"""

import time
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys

from pages.social.base_social_page import BaseSocialPage
from utils.logger import get_logger

log = get_logger(__name__)


class FacebookPage(BaseSocialPage):

    PLATFORM_NAME = "Facebook"
    LOGIN_URL = "https://www.facebook.com/"

    _EMAIL    = (By.CSS_SELECTOR, "#email, input[name='email'], input[type='email']")
    _PASSWORD = (By.CSS_SELECTOR, "#pass, input[name='pass'], input[type='password']")
    _SUBMIT   = (By.CSS_SELECTOR, "button[name='login'], input[type='submit'][name='login'], button[type='submit']")
    _LOGGED_IN = (By.CSS_SELECTOR, "[aria-label='Your profile'], [data-testid='blue_bar_profile_link'], .x1i10hfl[href*='/me']")

    def login(self, username: str, password: str) -> bool:
        try:
            self.navigate(self.LOGIN_URL, wait_seconds=3)

            # Accept cookies if prompted
            self._dismiss_cookie_dialog()

            email_el = self._find_visible(*self._EMAIL, timeout=15)
            if not email_el:
                log.error("[Facebook] Email field not found.")
                return False
            self._type_into(email_el, username)

            pass_el = self._find_visible(*self._PASSWORD, timeout=10)
            if not pass_el:
                log.error("[Facebook] Password field not found.")
                return False
            self._type_into(pass_el, password)

            # Click login button
            if not self._click(*self._SUBMIT, timeout=8):
                pass_el.send_keys(Keys.RETURN)

            time.sleep(5)

            if self.is_logged_in():
                log.info("[Facebook] ✅ Login successful.")
                return True

            # Handle 2FA or checkpoint
            current = self._current_url()
            if "checkpoint" in current or "two_step" in current or "login_approvals" in current:
                log.warning("[Facebook] Security check detected. Waiting 20s for manual action.")
                time.sleep(20)
                return self.is_logged_in()

            log.error("[Facebook] Login verification failed.")
            self._screenshot("login_failed")
            return False

        except Exception as exc:
            log.error(f"[Facebook] Login error: {exc}")
            self._screenshot("login_error")
            return False

    def _dismiss_cookie_dialog(self) -> None:
        """Dismiss GDPR / cookie consent popup if present."""
        cookie_btn_xpaths = [
            "//button[contains(normalize-space(.),'Allow all cookies')]",
            "//button[contains(normalize-space(.),'Accept all')]",
            "//button[contains(normalize-space(.),'Accept')]",
            "//button[@data-cookiebanner='accept_button']",
        ]
        for xp in cookie_btn_xpaths:
            try:
                if self._click(By.XPATH, xp, timeout=3):
                    time.sleep(1)
                    return
            except Exception:
                continue

    def is_logged_in(self) -> bool:
        try:
            url = self._current_url()
            if "login" in url and "facebook.com" in url:
                return False
            el = self._find(*self._LOGGED_IN, timeout=5)
            if el:
                return True
            # Fallback: check for home feed elements
            feed = self._find(By.CSS_SELECTOR, "[role='feed'], [data-pagelet='FeedUnit']", timeout=5)
            return feed is not None
        except Exception:
            return False

    def post_comment(self, url: str, comment_text: str) -> bool:
        """Navigate to a Facebook post and add a comment."""
        try:
            self.navigate(url, wait_seconds=4)
            self._dismiss_cookie_dialog()

            # Click "Write a comment…" or similar to activate the input
            comment_placeholders = [
                (By.XPATH, "//div[@aria-label='Write a comment…' or @aria-label='Write a comment' or @aria-placeholder='Write a comment…']"),
                (By.CSS_SELECTOR, "div[aria-label*='comment'][contenteditable='true']"),
                (By.CSS_SELECTOR, "div[data-lexical-editor='true']"),
                (By.XPATH, "//div[contains(@class,'comment') and @contenteditable='true']"),
            ]

            comment_box = None
            for by, sel in comment_placeholders:
                el = self._find_visible(by, sel, timeout=8)
                if el:
                    comment_box = el
                    break

            if comment_box is None:
                # Try clicking a "Comment" button first to reveal the box
                self._click(By.XPATH, "//div[@aria-label='Leave a comment' or @role='button'][contains(.,'Comment')]", timeout=5)
                time.sleep(1)
                for by, sel in comment_placeholders:
                    el = self._find_visible(by, sel, timeout=5)
                    if el:
                        comment_box = el
                        break

            if comment_box is None:
                log.error("[Facebook] Comment box not found.")
                self._screenshot("comment_not_found")
                return False

            comment_box.click()
            time.sleep(0.5)
            comment_box.send_keys(comment_text)
            time.sleep(0.5)

            # Submit with Enter or button
            comment_box.send_keys(Keys.RETURN)
            time.sleep(2)

            log.info("[Facebook] ✅ Comment submitted.")
            return True

        except Exception as exc:
            log.error(f"[Facebook] post_comment error: {exc}")
            self._screenshot("post_error")
            return False
