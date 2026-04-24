"""
pages/social/linkedin_page.py
==============================
Handles LinkedIn login and comment posting on posts/articles.
"""

import time
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys

from pages.social.base_social_page import BaseSocialPage
from utils.logger import get_logger

log = get_logger(__name__)


class LinkedInPage(BaseSocialPage):

    PLATFORM_NAME = "LinkedIn"
    LOGIN_URL = "https://www.linkedin.com/login"

    _EMAIL    = (By.CSS_SELECTOR, "#username, input[name='session_key'], input[type='email']")
    _PASSWORD = (By.CSS_SELECTOR, "#password, input[name='session_password'], input[type='password']")
    _SUBMIT   = (By.CSS_SELECTOR, "button[type='submit'], .sign-in-form__submit-button")
    _LOGGED_IN = (By.CSS_SELECTOR, ".global-nav__me, [data-control-name='identity_welcome_message'], nav .profile-rail-card")

    def login(self, username: str, password: str) -> bool:
        try:
            self.navigate(self.LOGIN_URL, wait_seconds=3)

            email_el = self._find_visible(*self._EMAIL, timeout=15)
            if not email_el:
                log.error("[LinkedIn] Email field not found.")
                return False
            self._type_into(email_el, username)

            pass_el = self._find_visible(*self._PASSWORD, timeout=10)
            if not pass_el:
                log.error("[LinkedIn] Password field not found.")
                return False
            self._type_into(pass_el, password)
            pass_el.send_keys(Keys.RETURN)

            time.sleep(5)

            if self.is_logged_in():
                log.info("[LinkedIn] ✅ Login successful.")
                return True

            # Handle security check page
            current = self._current_url()
            if "checkpoint" in current or "challenge" in current:
                log.warning("[LinkedIn] Security checkpoint detected. Manual intervention may be needed.")
                time.sleep(15)  # Give user time to solve
                return self.is_logged_in()

            log.error("[LinkedIn] Login verification failed.")
            self._screenshot("login_failed")
            return False

        except Exception as exc:
            log.error(f"[LinkedIn] Login error: {exc}")
            self._screenshot("login_error")
            return False

    def is_logged_in(self) -> bool:
        try:
            url = self._current_url()
            if "login" in url or "authwall" in url:
                return False
            el = self._find(*self._LOGGED_IN, timeout=5)
            return el is not None
        except Exception:
            return False

    def post_comment(self, url: str, comment_text: str) -> bool:
        """Post a comment on a LinkedIn post or article."""
        try:
            self.navigate(url, wait_seconds=4)

            # Click the comment button/area to activate the comment box
            comment_triggers = [
                (By.CSS_SELECTOR, ".comment-button, button[aria-label*='comment'], .social-actions__button--comment"),
                (By.XPATH, "//button[contains(@aria-label,'comment') or contains(normalize-space(.),'Comment')]"),
                (By.CSS_SELECTOR, ".comments-comment-box__form"),
            ]

            for by, sel in comment_triggers:
                if self._click(by, sel, timeout=5):
                    time.sleep(1)
                    break

            # Find the comment input
            editor_selectors = [
                ".ql-editor[contenteditable='true']",
                ".comments-comment-box__text-editor [contenteditable='true']",
                "div[contenteditable='true'][role='textbox']",
                "div[contenteditable='true']",
            ]

            for sel in editor_selectors:
                try:
                    editor = self._find_visible(By.CSS_SELECTOR, sel, timeout=8)
                    if editor:
                        editor.click()
                        time.sleep(0.3)
                        editor.send_keys(comment_text)
                        time.sleep(0.5)

                        # Submit with Ctrl+Enter or button
                        submitted = False

                        # Try submit button first
                        submit_selectors = [
                            "button.comments-comment-box__submit-button",
                            "button[class*='submit']",
                            ".comments-comment-texteditor ~ * button[type='submit']",
                        ]
                        for sub_sel in submit_selectors:
                            if self._click(By.CSS_SELECTOR, sub_sel, timeout=5):
                                submitted = True
                                break

                        if not submitted:
                            editor.send_keys(Keys.CONTROL, Keys.RETURN)
                            submitted = True

                        if submitted:
                            log.info("[LinkedIn] ✅ Comment submitted.")
                            time.sleep(2)
                            return True
                except Exception:
                    continue

            log.error("[LinkedIn] Comment box not found.")
            self._screenshot("comment_not_found")
            return False

        except Exception as exc:
            log.error(f"[LinkedIn] post_comment error: {exc}")
            self._screenshot("post_error")
            return False