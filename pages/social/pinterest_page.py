"""
pages/social/pinterest_page.py
================================
Handles Pinterest login and comment posting on pins.
"""

import time
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys

from pages.social.base_social_page import BaseSocialPage
from utils.logger import get_logger

log = get_logger(__name__)


class PinterestPage(BaseSocialPage):

    PLATFORM_NAME = "Pinterest"
    LOGIN_URL = "https://www.pinterest.ph/login/"

    _EMAIL    = (By.CSS_SELECTOR, "input[id='email'], input[name='id'], input[type='email']")
    _PASSWORD = (By.CSS_SELECTOR, "input[id='password'], input[name='password'], input[type='password']")
    _SUBMIT   = (By.CSS_SELECTOR, "button[type='submit'], .red.SignupButton, div[data-test-id='registerFormSubmitButton']")
    _LOGGED_IN = (By.CSS_SELECTOR, "[data-test-id='header-avatar'], [aria-label='Your profile and account info'], a[href*='/user/']")

    def login(self, username: str, password: str) -> bool:
        try:
            self.navigate(self.LOGIN_URL, wait_seconds=3)

            email_el = self._find_visible(*self._EMAIL, timeout=15)
            if not email_el:
                log.error("[Pinterest] Email field not found.")
                return False
            self._type_into(email_el, username)

            pass_el = self._find_visible(*self._PASSWORD, timeout=10)
            if not pass_el:
                log.error("[Pinterest] Password field not found.")
                return False
            self._type_into(pass_el, password)

            if not self._click(*self._SUBMIT, timeout=8):
                pass_el.send_keys(Keys.RETURN)

            time.sleep(5)

            if self.is_logged_in():
                log.info("[Pinterest] ✅ Login successful.")
                return True

            log.error("[Pinterest] Login verification failed.")
            self._screenshot("login_failed")
            return False

        except Exception as exc:
            log.error(f"[Pinterest] Login error: {exc}")
            self._screenshot("login_error")
            return False

    def is_logged_in(self) -> bool:
        try:
            url = self._current_url()
            if "login" in url:
                return False
            el = self._find(*self._LOGGED_IN, timeout=5)
            return el is not None
        except Exception:
            return False

    def post_comment(self, url: str, comment_text: str) -> bool:
        """Navigate to a Pinterest pin and add a comment."""
        try:
            self.navigate(url, wait_seconds=4)

            # Find comment input
            comment_selectors = [
                "[data-test-id='CloseupMainPin'] textarea",
                "textarea[placeholder*='comment']",
                "textarea[aria-label*='comment']",
                "div[data-test-id='comment-box-input'] textarea",
                "textarea",
            ]

            comment_box = None
            for sel in comment_selectors:
                el = self._find_visible(By.CSS_SELECTOR, sel, timeout=8)
                if el:
                    comment_box = el
                    break

            if comment_box is None:
                # Try clicking a comment icon to reveal box
                comment_icon_selectors = [
                    "[data-test-id='CloseupMainPin'] [aria-label*='comment']",
                    "button[aria-label*='comment']",
                ]
                for sel in comment_icon_selectors:
                    if self._click(By.CSS_SELECTOR, sel, timeout=5):
                        time.sleep(1)
                        for sel2 in comment_selectors:
                            el = self._find_visible(By.CSS_SELECTOR, sel2, timeout=5)
                            if el:
                                comment_box = el
                                break
                        break

            if comment_box is None:
                log.error("[Pinterest] Comment box not found.")
                self._screenshot("comment_not_found")
                return False

            comment_box.click()
            time.sleep(0.3)
            comment_box.send_keys(comment_text)
            time.sleep(0.5)

            # Submit
            submit_selectors = [
                "[data-test-id='comment-box-send-button']",
                "button[aria-label='Post comment']",
                "button[type='submit']",
            ]
            for sel in submit_selectors:
                if self._click(By.CSS_SELECTOR, sel, timeout=5):
                    log.info("[Pinterest] ✅ Comment submitted.")
                    time.sleep(2)
                    return True

            comment_box.send_keys(Keys.RETURN)
            log.info("[Pinterest] ✅ Comment submitted (Enter).")
            return True

        except Exception as exc:
            log.error(f"[Pinterest] post_comment error: {exc}")
            self._screenshot("post_error")
            return False
