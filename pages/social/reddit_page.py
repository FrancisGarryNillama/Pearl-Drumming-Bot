"""
pages/social/reddit_page.py
============================
Handles Reddit login and comment posting.
Supports both old.reddit.com and new Reddit UI.
"""

import time
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys

from pages.social.base_social_page import BaseSocialPage
from utils.logger import get_logger

log = get_logger(__name__)


class RedditPage(BaseSocialPage):

    PLATFORM_NAME = "Reddit"
    LOGIN_URL = "https://www.reddit.com/login/"

    # ── Locators ────────────────────────────────────────────
    _USERNAME   = (By.CSS_SELECTOR, "#loginUsername, input[name='username']")
    _PASSWORD   = (By.CSS_SELECTOR, "#loginPassword, input[name='password']")
    _SUBMIT     = (By.CSS_SELECTOR, "button[type='submit']")
    _USER_AVATAR = (By.CSS_SELECTOR, "#USER_DROPDOWN_ID, [data-testid='profile-link'], .user-info a[href*='/user/']")

    def login(self, username: str, password: str) -> bool:
        try:
            self.navigate(self.LOGIN_URL, wait_seconds=3)

            user_el = self._find_visible(*self._USERNAME, timeout=15)
            if not user_el:
                log.error("[Reddit] Username field not found.")
                return False
            self._type_into(user_el, username)

            pass_el = self._find_visible(*self._PASSWORD, timeout=10)
            if not pass_el:
                log.error("[Reddit] Password field not found.")
                return False
            self._type_into(pass_el, password)
            pass_el.send_keys(Keys.RETURN)

            time.sleep(4)

            if self.is_logged_in():
                log.info("[Reddit] ✅ Login successful.")
                return True

            log.error("[Reddit] Login verification failed.")
            self._screenshot("login_failed")
            return False

        except Exception as exc:
            log.error(f"[Reddit] Login error: {exc}")
            self._screenshot("login_error")
            return False

    def is_logged_in(self) -> bool:
        try:
            url = self._current_url()
            if "login" in url:
                return False
            # Check for user avatar / profile link
            el = self._find(*self._USER_AVATAR, timeout=5)
            return el is not None
        except Exception:
            return False

    def post_comment(self, url: str, comment_text: str) -> bool:
        """Navigate to a Reddit post and submit a top-level comment."""
        try:
            self.navigate(url, wait_seconds=3)

            # Scroll down to comment area
            self.driver.execute_script("window.scrollTo(0, 600);")
            time.sleep(1)

            # Strategy 1: New Reddit UI — contenteditable comment box
            if self._try_new_reddit_comment(comment_text):
                return True

            # Strategy 2: Old Reddit textarea
            if self._try_old_reddit_comment(comment_text):
                return True

            log.error("[Reddit] Could not locate comment box.")
            self._screenshot("comment_box_not_found")
            return False

        except Exception as exc:
            log.error(f"[Reddit] post_comment error: {exc}")
            self._screenshot("post_comment_error")
            return False

    def _try_new_reddit_comment(self, text: str) -> bool:
        """New Reddit (2023+) uses a contenteditable editor."""
        # Click the "Add a comment" placeholder to activate editor
        placeholder_selectors = [
            "[data-testid='comment-submit-button']",
            ".CommentFormByline",
            "div[data-click-id='text'] [contenteditable='true']",
            "[placeholder='Add a comment']",
            ".public-DraftEditorPlaceholder-root",
        ]

        for sel in placeholder_selectors:
            try:
                el = self._find_clickable(By.CSS_SELECTOR, sel, timeout=5)
                if el:
                    el.click()
                    time.sleep(0.5)
                    break
            except Exception:
                continue

        # Find the active contenteditable
        editor_selectors = [
            "div[contenteditable='true'][data-contents='true']",
            ".public-DraftEditor-content[contenteditable='true']",
            "div[role='textbox'][contenteditable='true']",
            "div[contenteditable='true']",
        ]

        for sel in editor_selectors:
            try:
                editor = self._find_visible(By.CSS_SELECTOR, sel, timeout=5)
                if editor:
                    editor.click()
                    time.sleep(0.3)
                    # Use keyboard shortcut to select all and replace
                    editor.send_keys(Keys.CONTROL, 'a')
                    editor.send_keys(text)
                    time.sleep(0.5)

                    # Click submit button
                    submit_selectors = [
                        "button[data-testid='comment-submit-button']",
                        "button.submit",
                        "button[type='submit']",
                    ]
                    for sub_sel in submit_selectors:
                        if self._click(By.CSS_SELECTOR, sub_sel, timeout=5):
                            log.info("[Reddit] ✅ Comment submitted (new UI).")
                            return True
            except Exception:
                continue

        return False

    def _try_old_reddit_comment(self, text: str) -> bool:
        """Old Reddit uses a plain <textarea>."""
        textarea = self._find_visible(
            By.CSS_SELECTOR,
            "textarea[name='text'], .usertext-edit textarea",
            timeout=5
        )
        if not textarea:
            return False

        self._type_into(textarea, text)
        time.sleep(0.3)

        # Submit
        submit = self._find_clickable(
            By.CSS_SELECTOR,
            "button.save, button[type='submit'], .submit",
            timeout=5
        )
        if submit:
            submit.click()
            log.info("[Reddit] ✅ Comment submitted (old UI).")
            time.sleep(2)
            return True

        return False
