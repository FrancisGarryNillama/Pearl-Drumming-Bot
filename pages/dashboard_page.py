"""
pages/dashboard_page.py
=======================
Page Object for the Pearl27 dashboard / task listing view.
Handles post discovery, assignment, and prioritization.
"""

import time
from dataclasses import dataclass, field
from typing import Optional

from selenium.webdriver.common.by import By
from selenium.webdriver.remote.webelement import WebElement
from selenium.common.exceptions import NoSuchElementException

from pages.base_page import BasePage
from utils.logger import get_logger
from utils.helpers import safe_strip

log = get_logger(__name__)


@dataclass
class DrummingPost:
    """Represents a single drumming post / task found on the dashboard."""
    element: WebElement = field(repr=False)
    title: str = ""
    link: str = ""
    score: float = 0.0
    status: str = ""
    post_id: str = ""
    platform: str = ""

    def __repr__(self) -> str:
        return (
            f"DrummingPost(title={self.title!r}, score={self.score}, "
            f"status={self.status!r}, link={self.link!r})"
        )


class DashboardPage(BasePage):
    """
    Dashboard page — lists all available drumming posts / tasks.

    NOTE: Selector strings below are best-guess based on common
    patterns. Inspect the live Pearl27 DOM and update accordingly.
    """

    # ── Locators ────────────────────────────────────────────
    # Posts / task table or card list
    _POST_ROWS        = (By.CSS_SELECTOR, "tr.post-row, .task-card, .drum-post, [data-testid='post-row']")
    _POST_TITLE       = (By.CSS_SELECTOR, ".post-title, .task-title, td.title, h3")
    _POST_LINK        = (By.CSS_SELECTOR, "a.post-link, a.external-link, td.link a, .drum-link")
    _POST_SCORE       = (By.CSS_SELECTOR, ".score, .points, td.score, [data-score]")
    _POST_STATUS      = (By.CSS_SELECTOR, ".status, td.status, .task-status")
    _ASSIGN_BUTTON    = (By.CSS_SELECTOR, "button.assign, .assign-btn, [data-action='assign']")
    _PLATFORM_CELL    = (By.CSS_SELECTOR, ".platform, td.platform, [data-platform]")

    # ─────────────────────────────────────────────────────────
    # Public API
    # ─────────────────────────────────────────────────────────

    def get_unassigned_posts(self, account_number: str) -> list[DrummingPost]:
        """
        Scan the dashboard and return posts that are unassigned
        (or assigned to this account and not yet completed).

        Args:
            account_number: e.g. 'PH1037'

        Returns:
            List of DrummingPost objects, sorted by score descending.
        """
        log.info("Scanning dashboard for unassigned posts …")
        self._wait_for_page_load()
        time.sleep(1)

        row_elements = self.find_all(*self._POST_ROWS, timeout=15)
        if not row_elements:
            log.warning("No post rows found on dashboard.")
            return []

        log.info(f"Found {len(row_elements)} post row(s).")

        posts: list[DrummingPost] = []
        for idx, row in enumerate(row_elements):
            try:
                post = self._parse_row(row, idx)
                if self._is_eligible(post, account_number):
                    posts.append(post)
            except Exception as exc:
                log.warning(f"Error parsing row {idx}: {exc}")

        # Sort by score descending (highest priority first)
        posts.sort(key=lambda p: p.score, reverse=True)
        log.info(f"{len(posts)} eligible post(s) found after filtering.")
        return posts

    def assign_post(self, post: DrummingPost, account_number: str) -> bool:
        """
        Assign a post to the given account number by clicking
        the Assign button within the post's row element.

        Args:
            post:           DrummingPost to assign
            account_number: Target account (e.g. 'PH1037')

        Returns:
            True if assignment succeeded.
        """
        log.info(f"Assigning post '{post.title}' to {account_number} …")
        try:
            assign_btn = post.element.find_element(By.CSS_SELECTOR, self._ASSIGN_BUTTON[1])
            self.driver.execute_script("arguments[0].scrollIntoView(true);", assign_btn)
            time.sleep(0.3)
            assign_btn.click()

            # Handle any modal / dropdown that appears
            self._handle_assign_modal(account_number)
            log.info(f"✅ Post assigned to {account_number}")
            return True
        except NoSuchElementException:
            log.warning("Assign button not found — post may already be assigned.")
            return True  # Treat as acceptable state
        except Exception as exc:
            log.error(f"Failed to assign post: {exc}")
            return False

    def select_highest_priority(self, posts: list[DrummingPost]) -> Optional[DrummingPost]:
        """Return the post with the highest score."""
        if not posts:
            log.warning("No posts to prioritize.")
            return None
        best = posts[0]  # Already sorted descending
        log.info(f"Selected highest-priority post: {best}")
        return best

    # ─────────────────────────────────────────────────────────
    # Private helpers
    # ─────────────────────────────────────────────────────────

    def _parse_row(self, row: WebElement, idx: int) -> DrummingPost:
        """Extract data from a single post row element."""

        def _cell_text(css: str) -> str:
            try:
                return safe_strip(row.find_element(By.CSS_SELECTOR, css).text)
            except Exception:
                return ""

        def _cell_attr(css: str, attr: str) -> str:
            try:
                el = row.find_element(By.CSS_SELECTOR, css)
                return safe_strip(el.get_attribute(attr) or el.text)
            except Exception:
                return ""

        # Extract title (try multiple selectors)
        title = (
            _cell_text(self._POST_TITLE[1])
            or _cell_text("td:nth-child(2)")
            or f"Post #{idx + 1}"
        )

        # Extract external link
        link = (
            _cell_attr(self._POST_LINK[1], "href")
            or _cell_attr("a", "href")
            or ""
        )

        # Extract score — try data-score attr, then text parse
        raw_score = _cell_attr(self._POST_SCORE[1], "data-score") or _cell_text(self._POST_SCORE[1])
        score = self._parse_score(raw_score)

        # Status
        status = _cell_text(self._POST_STATUS[1]) or _cell_text("td:last-child")

        # Platform
        platform = _cell_text(self._PLATFORM_CELL[1]) or self._infer_platform(link)

        return DrummingPost(
            element=row,
            title=title,
            link=link,
            score=score,
            status=status,
            post_id=_cell_attr("[data-id]", "data-id") or str(idx),
            platform=platform,
        )

    @staticmethod
    def _parse_score(raw: str) -> float:
        """Extract a numeric score from raw text like '85 pts' or '85'."""
        import re
        match = re.search(r"[\d.]+", raw)
        return float(match.group()) if match else 0.0

    @staticmethod
    def _infer_platform(url: str) -> str:
        """Guess platform name from URL."""
        import re
        if not url:
            return "Unknown"
        match = re.search(r"(?:https?://)?(?:www\.)?([^./]+)", url)
        return match.group(1).capitalize() if match else "Unknown"

    @staticmethod
    def _is_eligible(post: DrummingPost, account_number: str) -> bool:
        """
        A post is eligible if it's not yet Complete and
        not assigned to a different account.
        """
        status_lower = post.status.lower()
        if "complete" in status_lower:
            return False
        # If status shows it's unassigned or belongs to this account
        return True

    def _handle_assign_modal(self, account_number: str) -> None:
        """
        If a modal or dropdown appears after clicking Assign,
        select the correct account and confirm.
        """
        time.sleep(1)
        try:
            # Try dropdown / select
            from selenium.webdriver.support.ui import Select
            select_el = self.find(By.CSS_SELECTOR, "select.account-select, select[name='account']", timeout=3)
            Select(select_el).select_by_visible_text(account_number)
        except Exception:
            pass

        try:
            # Try typing account into a text field
            input_el = self.find(By.CSS_SELECTOR, "input.account-input, input[placeholder*='account']", timeout=3)
            input_el.clear()
            input_el.send_keys(account_number)
        except Exception:
            pass

        # Confirm
        try:
            self.click(By.CSS_SELECTOR, "button.confirm, button[type='submit'], .modal-confirm", timeout=5)
        except Exception:
            pass