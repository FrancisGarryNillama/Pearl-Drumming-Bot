"""
pages/social/quora_page.py
===========================
Handles Quora login and answer/comment posting.
Quora is JavaScript-heavy — always uses Selenium.
"""

import time
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys

from pages.social.base_social_page import BaseSocialPage
from utils.logger import get_logger

log = get_logger(__name__)


class QuoraPage(BaseSocialPage):

    PLATFORM_NAME = "Quora"
    LOGIN_URL = "https://www.quora.com/login"

    _EMAIL    = (By.CSS_SELECTOR, "input[name='email'], input[type='email'], #email")
    _PASSWORD = (By.CSS_SELECTOR, "input[name='password'], input[type='password'], #password")
    _SUBMIT   = (By.CSS_SELECTOR, "button[type='submit'], .submit_button, .login_button")
    _LOGGED_IN_INDICATOR = (By.CSS_SELECTOR, "[class*='Header'] [class*='Avatar'], .profile_photo_img, img.avatar")

    def login(self, username: str, password: str) -> bool:
        try:
            self.navigate(self.LOGIN_URL, wait_seconds=3)

            email_el = self._find_visible(*self._EMAIL, timeout=15)
            if not email_el:
                log.error("[Quora] Email field not found.")
                return False
            self._type_into(email_el, username)

            pass_el = self._find_visible(*self._PASSWORD, timeout=10)
            if not pass_el:
                log.error("[Quora] Password field not found.")
                return False
            self._type_into(pass_el, password)
            pass_el.send_keys(Keys.RETURN)

            time.sleep(5)

            if self.is_logged_in():
                log.info("[Quora] ✅ Login successful.")
                return True

            log.error("[Quora] Login verification failed.")
            self._screenshot("login_failed")
            return False

        except Exception as exc:
            log.error(f"[Quora] Login error: {exc}")
            self._screenshot("login_error")
            return False

    def is_logged_in(self) -> bool:
        try:
            url = self._current_url()
            if "login" in url:
                return False
            el = self._find(*self._LOGGED_IN_INDICATOR, timeout=5)
            return el is not None
        except Exception:
            return False

    def post_comment(self, url: str, comment_text: str) -> bool:
        """
        Post an answer or comment on a Quora question/post.
        Tries to add an answer first; falls back to adding a comment.
        """
        try:
            self.navigate(url, wait_seconds=4)

            # Try posting an Answer (preferred on question pages)
            if self._try_post_answer(comment_text):
                return True

            # Fallback: post a comment
            if self._try_post_inline_comment(comment_text):
                return True

            log.error("[Quora] Could not find answer or comment box.")
            self._screenshot("comment_not_found")
            return False

        except Exception as exc:
            log.error(f"[Quora] post_comment error: {exc}")
            self._screenshot("post_error")
            return False

    def _try_post_answer(self, text: str) -> bool:
        """Click 'Answer' button and type into the answer editor."""
        answer_btn_selectors = [
            "button[class*='answer']",
            "[class*='AnswerButton']",
            "button span:contains('Answer')",
            ".qu-display--inline-flex button",
        ]
        answer_btn_xpaths = [
            "//button[contains(normalize-space(.),'Answer') and not(contains(@class,'comment'))]",
            "//a[contains(normalize-space(.),'Answer') and @role='button']",
        ]

        clicked = False
        for sel in answer_btn_selectors:
            if self._click(By.CSS_SELECTOR, sel, timeout=5):
                clicked = True
                break

        if not clicked:
            for xp in answer_btn_xpaths:
                if self._click(By.XPATH, xp, timeout=5):
                    clicked = True
                    break

        if not clicked:
            return False

        time.sleep(2)

        # Find the rich text editor
        editor_selectors = [
            "div[contenteditable='true']",
            ".doc[contenteditable='true']",
            "[class*='editor'] [contenteditable='true']",
            "div[role='textbox']",
        ]
        for sel in editor_selectors:
            try:
                editor = self._find_visible(By.CSS_SELECTOR, sel, timeout=8)
                if editor:
                    editor.click()
                    time.sleep(0.5)
                    editor.send_keys(text)
                    time.sleep(0.5)

                    # Submit
                    submit_xpaths = [
                        "//button[contains(normalize-space(.),'Submit')]",
                        "//button[contains(normalize-space(.),'Post')]",
                        "//button[@type='submit']",
                    ]
                    for xp in submit_xpaths:
                        if self._click(By.XPATH, xp, timeout=5):
                            log.info("[Quora] ✅ Answer submitted.")
                            time.sleep(2)
                            return True
            except Exception:
                continue

        return False

    def _try_post_inline_comment(self, text: str) -> bool:
        """Add a comment on an existing answer."""
        comment_xpaths = [
            "//button[contains(normalize-space(.),'Comment')]",
            "//span[contains(normalize-space(.),'Add comment')]",
        ]
        for xp in comment_xpaths:
            if self._click(By.XPATH, xp, timeout=5):
                time.sleep(1)
                break

        editor = self._find_visible(By.CSS_SELECTOR, "div[contenteditable='true']", timeout=8)
        if not editor:
            return False

        editor.click()
        editor.send_keys(text)
        time.sleep(0.5)

        submit_xpaths = [
            "//button[contains(normalize-space(.),'Submit')]",
            "//button[contains(normalize-space(.),'Post')]",
        ]
        for xp in submit_xpaths:
            if self._click(By.XPATH, xp, timeout=5):
                log.info("[Quora] ✅ Comment submitted.")
                return True

        return False
