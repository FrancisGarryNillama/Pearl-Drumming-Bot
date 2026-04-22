"""
pages/post_page.py
==================
Page Object for an individual drumming post detail view.
Handles comment submission and status workflow transitions.
"""

import time
from typing import Optional

from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.common.exceptions import NoSuchElementException, TimeoutException

from pages.base_page import BasePage
from utils.logger import get_logger

log = get_logger(__name__)


class PostPage(BasePage):
    """
    Manages interactions on the individual post / task detail page.

    NOTE: Selectors are placeholder patterns — inspect the live
    Pearl27 DOM and update to match actual element identifiers.
    """

    # ── Locators ────────────────────────────────────────────
    # Status controls
    _STATUS_DROPDOWN    = (By.CSS_SELECTOR, "select.status-select, [data-testid='status-dropdown'], .status-control select")
    _STATUS_BUTTON_TMPL = "button[data-status='{status}'], .status-btn[data-value='{status}']"
    _STATUS_LABEL       = (By.CSS_SELECTOR, ".current-status, .status-badge, [data-testid='post-status']")
    _STATUS_SAVE_BTN    = (By.CSS_SELECTOR, "button.save-status, .status-save, [data-action='save-status']")

    # Comment / reply area
    _COMMENT_BOX        = (By.CSS_SELECTOR, "textarea.comment-input, textarea[name='comment'], .reply-area textarea, #comment-text")
    _SUBMIT_COMMENT_BTN = (By.CSS_SELECTOR, "button.submit-comment, button[type='submit'].comment-btn, .post-reply-btn, .submit-reply")

    # Post detail
    _POST_TITLE         = (By.CSS_SELECTOR, "h1.post-title, .post-header h1, [data-testid='post-title']")
    _POST_PLATFORM      = (By.CSS_SELECTOR, ".platform-badge, [data-platform], .post-platform")
    _EXTERNAL_LINK      = (By.CSS_SELECTOR, "a.external-post-link, .post-source-link, [data-testid='external-link']")

    # ─────────────────────────────────────────────────────────
    # Status Workflow
    # ─────────────────────────────────────────────────────────

    def advance_status(self, status_flow: list[str]) -> bool:
        """
        Walk through every status in the flow sequentially,
        applying each transition on the current post.

        Args:
            status_flow: Ordered list e.g.
                         ['Not Ready', 'Draft Ready', 'Approved', 'Complete']

        Returns:
            True if all transitions completed successfully.
        """
        for i in range(len(status_flow) - 1):
            from_status = status_flow[i]
            to_status   = status_flow[i + 1]
            log.info(f"Status transition: '{from_status}' → '{to_status}'")

            success = self._set_status(to_status)
            if not success:
                log.error(f"Failed to set status to '{to_status}'")
                return False

            time.sleep(1)  # Brief pause between transitions

        log.info("✅ All status transitions completed.")
        return True

    def _set_status(self, target_status: str) -> bool:
        """
        Attempt to set the post status via dropdown or button.

        Strategy:
        1. Try a <select> dropdown
        2. Try labelled buttons
        3. Try clicking a status label that triggers a picker
        """
        # Strategy 1: <select> dropdown
        try:
            from selenium.webdriver.support.ui import Select
            select_el = self.find(*self._STATUS_DROPDOWN, timeout=5)
            Select(select_el).select_by_visible_text(target_status)
            self._save_status()
            log.debug(f"Status set via dropdown: {target_status}")
            return True
        except Exception:
            pass

        # Strategy 2: Direct status button
        try:
            btn_selector = self._STATUS_BUTTON_TMPL.format(status=target_status)
            self.click(By.CSS_SELECTOR, btn_selector, timeout=5)
            self._save_status()
            log.debug(f"Status set via button: {target_status}")
            return True
        except Exception:
            pass

        # Strategy 3: Click current status label → pick from list
        try:
            self.click(*self._STATUS_LABEL, timeout=5)
            time.sleep(0.5)
            # Look for the option in the revealed picker
            option = self.find(
                By.XPATH,
                f"//*[contains(text(),'{target_status}')]",
                timeout=5,
            )
            option.click()
            self._save_status()
            log.debug(f"Status set via picker: {target_status}")
            return True
        except Exception:
            pass

        log.warning(f"Could not set status to '{target_status}' via any strategy.")
        return False

    def _save_status(self) -> None:
        """Click a Save / Confirm button if it appears after status change."""
        try:
            self.click(*self._STATUS_SAVE_BTN, timeout=3)
            time.sleep(0.5)
        except Exception:
            pass  # Not all UIs require explicit save

    # ─────────────────────────────────────────────────────────
    # Comment / Reply
    # ─────────────────────────────────────────────────────────

    def submit_comment(self, comment_text: str) -> bool:
        """
        Type and submit a comment / reply on the current post.

        Args:
            comment_text: The generated LLM comment to post

        Returns:
            True if submitted successfully.
        """
        log.info(f"Submitting comment ({len(comment_text)} chars) …")

        # Locate and clear the comment textarea
        textarea = None
        for sel in self._COMMENT_BOX[1].split(","):
            sel = sel.strip()
            try:
                textarea = self.find_visible(By.CSS_SELECTOR, sel, timeout=8)
                break
            except Exception:
                continue

        if textarea is None:
            log.error("Comment textarea not found.")
            self.take_screenshot("logs/comment_box_not_found.png")
            return False

        try:
            textarea.clear()
            textarea.click()
            time.sleep(0.3)
            # Type slowly to avoid JS input-event drops
            textarea.send_keys(comment_text)
            time.sleep(0.5)

            log.info("Comment typed. Submitting …")
            self._click_submit_comment()
            log.info("✅ Comment submitted.")
            return True
        except Exception as exc:
            log.error(f"Failed to submit comment: {exc}")
            self.take_screenshot("logs/comment_submit_failure.png")
            return False

    def _click_submit_comment(self) -> None:
        """Click the comment submit button or press Ctrl+Enter."""
        for sel in self._SUBMIT_COMMENT_BTN[1].split(","):
            sel = sel.strip()
            try:
                self.click(By.CSS_SELECTOR, sel, timeout=5)
                return
            except Exception:
                continue
        # Fallback: Ctrl+Enter in the textarea
        try:
            textarea = self.find(*self._COMMENT_BOX)
            textarea.send_keys(Keys.CONTROL, Keys.RETURN)
        except Exception:
            log.warning("Could not submit comment via any method.")

    # ─────────────────────────────────────────────────────────
    # Info Extraction
    # ─────────────────────────────────────────────────────────

    def get_external_link(self) -> str:
        """Return the href of the external post link, if present."""
        return self.get_attribute(*self._EXTERNAL_LINK, attr="href")

    def get_platform_name(self) -> str:
        """Return the platform name shown on the post."""
        return self.get_text(*self._POST_PLATFORM, default="Unknown")

    def get_post_url(self) -> str:
        """Return the current page URL as the post URL."""
        return self.driver.current_url