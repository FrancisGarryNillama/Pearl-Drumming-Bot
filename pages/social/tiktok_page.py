"""
pages/social/tiktok_page.py
============================
Handles TikTok login and comment posting.
TikTok has heavy bot detection — uses email/password login flow.
"""

import time
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys

from pages.social.base_social_page import BaseSocialPage
from utils.logger import get_logger

log = get_logger(__name__)


class TikTokPage(BaseSocialPage):

    PLATFORM_NAME = "TikTok"
    LOGIN_URL = "https://www.tiktok.com/login/phone-or-email/email"

    _EMAIL_TAB    = (By.XPATH, "//a[contains(normalize-space(.),'Email') or contains(normalize-space(.),'Use email')]")
    _EMAIL_FIELD  = (By.CSS_SELECTOR, "input[name='username'], input[type='email'], input[placeholder*='Email'], input[placeholder*='email']")
    _PASSWORD_FIELD = (By.CSS_SELECTOR, "input[type='password'], input[name='password'], input[placeholder*='Password']")
    _SUBMIT       = (By.CSS_SELECTOR, "button[type='submit'], button[data-e2e='login-button'], .tiktok-btn-pc-primary")
    _LOGGED_IN    = (By.CSS_SELECTOR, "[data-e2e='profile-icon'], [data-e2e='nav-profile'], .avatar-wrapper")

    def login(self, username: str, password: str) -> bool:
        try:
            self.navigate(self.LOGIN_URL, wait_seconds=3)

            # TikTok may show phone tab by default — switch to email
            self._switch_to_email_tab()
            time.sleep(1)

            email_el = self._find_visible(*self._EMAIL_FIELD, timeout=15)
            if not email_el:
                log.error("[TikTok] Email field not found.")
                self._screenshot("login_no_email")
                return False
            self._type_into(email_el, username, slow=True)

            pass_el = self._find_visible(*self._PASSWORD_FIELD, timeout=10)
            if not pass_el:
                log.error("[TikTok] Password field not found.")
                return False
            self._type_into(pass_el, password, slow=True)

            time.sleep(0.5)

            if not self._click(*self._SUBMIT, timeout=8):
                pass_el.send_keys(Keys.RETURN)

            time.sleep(6)

            # TikTok may show a CAPTCHA — wait longer
            if not self.is_logged_in():
                log.warning("[TikTok] Possible CAPTCHA. Waiting 15s for manual resolution.")
                time.sleep(15)

            if self.is_logged_in():
                log.info("[TikTok] ✅ Login successful.")
                return True

            log.error("[TikTok] Login verification failed.")
            self._screenshot("login_failed")
            return False

        except Exception as exc:
            log.error(f"[TikTok] Login error: {exc}")
            self._screenshot("login_error")
            return False

    def _switch_to_email_tab(self) -> None:
        """Click the 'Log in with email' option if visible."""
        selectors = [
            (By.XPATH, "//a[contains(normalize-space(.),'email') or contains(normalize-space(.),'Email')]"),
            (By.CSS_SELECTOR, "a[href*='email']"),
        ]
        for by, sel in selectors:
            if self._click(by, sel, timeout=5):
                time.sleep(0.5)
                return

    def is_logged_in(self) -> bool:
        try:
            url = self._current_url()
            if "login" in url:
                return False
            el = self._find(*self._LOGGED_IN, timeout=8)
            return el is not None
        except Exception:
            return False

    def post_comment(self, url: str, comment_text: str) -> bool:
        """Navigate to a TikTok video and post a comment."""
        try:
            self.navigate(url, wait_seconds=5)

            # Scroll down to comments
            self.driver.execute_script("window.scrollTo(0, 500);")
            time.sleep(1)

            # Find the comment input
            comment_selectors = [
                "[data-e2e='comment-input']",
                "div[contenteditable='true'][class*='comment']",
                "div[contenteditable='true'][placeholder*='comment']",
                "div[contenteditable='true'][placeholder*='Comment']",
                "div[data-e2e='comment-box']",
            ]

            comment_box = None
            for sel in comment_selectors:
                el = self._find_visible(By.CSS_SELECTOR, sel, timeout=8)
                if el:
                    comment_box = el
                    break

            # Try clicking a "Add comment" area first
            if comment_box is None:
                click_targets = [
                    "[data-e2e='comment-placeholder']",
                    "div[class*='InputAreaContainer']",
                    "div[class*='CommentPost']",
                ]
                for sel in click_targets:
                    if self._click(By.CSS_SELECTOR, sel, timeout=5):
                        time.sleep(1)
                        for sel2 in comment_selectors:
                            el = self._find_visible(By.CSS_SELECTOR, sel2, timeout=5)
                            if el:
                                comment_box = el
                                break
                        break

            if comment_box is None:
                log.error("[TikTok] Comment box not found.")
                self._screenshot("comment_not_found")
                return False

            comment_box.click()
            time.sleep(0.3)
            comment_box.send_keys(comment_text)
            time.sleep(0.5)

            # Submit
            submit_selectors = [
                "[data-e2e='comment-post']",
                "div[class*='PostButton']",
                "button[class*='post']",
            ]
            for sel in submit_selectors:
                if self._click(By.CSS_SELECTOR, sel, timeout=5):
                    log.info("[TikTok] ✅ Comment submitted.")
                    time.sleep(2)
                    return True

            # Fallback: Enter key
            comment_box.send_keys(Keys.RETURN)
            log.info("[TikTok] ✅ Comment submitted (Enter).")
            return True

        except Exception as exc:
            log.error(f"[TikTok] post_comment error: {exc}")
            self._screenshot("post_error")
            return False
