"""
pages/dashboard_page.py
=======================
Page Object for the Pearl27 dashboard / task listing view.
Handles post discovery, assignment, and prioritization.

Selectors updated to match the actual Pearl27 social-listening DOM.
"""

import time
import re
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

    Selectors based on the actual Pearl27 social-listening DOM:
    - Each post card is a div containing a .assignment-dropdown-container
    - Title is in an <h4> with a title attribute (full text) 
    - Score is a yellow button inside .assignment-dropdown-container
    - Status is a button showing e.g. "Not Ready"
    - External link is in a button's title attribute or an <a> href
    """

    _POST_CARDS = (By.CSS_SELECTOR, "div.assignment-dropdown-container")

    # ─────────────────────────────────────────────────────────
    # Public API
    # ─────────────────────────────────────────────────────────

    def get_unassigned_posts(self, account_number: str) -> list[DrummingPost]:
        """
        Scan the dashboard and return posts eligible for processing.

        Args:
            account_number: e.g. 'PH1037'

        Returns:
            List of DrummingPost objects, sorted by score descending.
        """
        log.info("Scanning dashboard for unassigned posts …")
        self._wait_for_page_load()
        time.sleep(2)

        card_containers = self.find_all(*self._POST_CARDS, timeout=15)

        if not card_containers:
            log.warning("No post cards found on dashboard.")
            return []

        # Walk up to the actual card root div for each container
        card_roots = []
        seen_ids = set()
        for container in card_containers:
            try:
                root = self.driver.execute_script(
                    """
                    var el = arguments[0];
                    // Walk up until we find a div with border-gray-200 in its class
                    while (el && el.parentElement) {
                        el = el.parentElement;
                        if (el.className && el.className.includes('border-gray-200')) {
                            return el;
                        }
                    }
                    // Fallback: return grandparent
                    return arguments[0].parentElement ? arguments[0].parentElement.parentElement : arguments[0];
                    """,
                    container
                )
                if root:
                    el_id = id(root)
                    if el_id not in seen_ids:
                        seen_ids.add(el_id)
                        card_roots.append(root)
            except Exception:
                card_roots.append(container)

        log.info(f"Found {len(card_roots)} post card(s).")

        posts: list[DrummingPost] = []
        for idx, card in enumerate(card_roots):
            try:
                post = self._parse_card(card, idx)
                log.debug(f"Parsed card {idx}: {post}")
                if self._is_eligible(post, account_number):
                    posts.append(post)
            except Exception as exc:
                log.warning(f"Error parsing card {idx}: {exc}")

        posts.sort(key=lambda p: p.score, reverse=True)
        log.info(f"{len(posts)} eligible post(s) found after filtering.")
        return posts

    def find_and_assign_best_post(self, account_number: str, min_score: float = 50.0, max_scan: int = 50) -> DrummingPost | None:
        """
        Efficiently find and assign the best eligible post without scanning all posts.

        Args:
            account_number: e.g. 'PH1037'
            min_score: Minimum acceptable score (stop scanning if found)
            max_scan: Maximum posts to scan before giving up

        Returns:
            The best eligible post found and assigned, or None if none found.
        """
        log.info(f"Scanning for best eligible post (min_score={min_score}, max_scan={max_scan}) …")
        self._wait_for_page_load()
        time.sleep(2)

        card_containers = self.find_all(*self._POST_CARDS, timeout=15)

        if not card_containers:
            log.warning("No post cards found on dashboard.")
            return None

        # Walk up to the actual card root div for each container (limit to max_scan)
        card_roots = []
        seen_ids = set()
        for container in card_containers[:max_scan]:  # Limit scanning
            try:
                root = self.driver.execute_script(
                    """
                    var el = arguments[0];
                    // Walk up until we find a div with border-gray-200 in its class
                    while (el && el.parentElement) {
                        el = el.parentElement;
                        if (el.className && el.className.includes('border-gray-200')) {
                            return el;
                        }
                    }
                    // Fallback: return grandparent
                    return arguments[0].parentElement ? arguments[0].parentElement.parentElement : arguments[0];
                    """,
                    container
                )
                if root:
                    el_id = id(root)
                    if el_id not in seen_ids:
                        seen_ids.add(el_id)
                        card_roots.append(root)
            except Exception:
                card_roots.append(container)

        log.info(f"Scanning {len(card_roots)} post card(s) for best eligible post…")

        best_post: DrummingPost | None = None

        for idx, card in enumerate(card_roots):
            try:
                post = self._parse_card(card, idx)
                log.debug(f"Parsed card {idx}: {post}")

                if self._is_eligible(post, account_number):
                    # Check if this is better than our current best
                    if best_post is None or post.score > best_post.score:
                        best_post = post
                        log.info(f"New best post found: {post.title[:50]} (score: {post.score})")

                        # If we found a post with high enough score, we can stop early
                        if post.score >= min_score:
                            log.info(f"Found post with score >= {min_score}, stopping scan early.")
                            break

            except Exception as exc:
                log.warning(f"Error parsing card {idx}: {exc}")

        if best_post:
            log.info(f"Best eligible post: {best_post.title[:50]} (score: {best_post.score})")
            # Assign the post immediately
            if self.assign_post(best_post, account_number):
                return best_post
            else:
                log.warning("Failed to assign the best post.")
                return None
        else:
            log.info("No eligible posts found within scan limit.")
            return None

    def assign_post(self, post: DrummingPost, account_number: str) -> bool:
        """Assign a post to the given account number."""
        log.info(f"Assigning post '{post.title[:50]}' to {account_number} …")
        try:
            assign_trigger = post.element.find_element(
                By.CSS_SELECTOR,
                "button[class*='bg-yellow'], .assignment-dropdown-container button"
            )
            
            # Scroll to element with offset to avoid header overlay
            self.driver.execute_script(
                "arguments[0].scrollIntoView({block: 'center', inline: 'center'});", 
                assign_trigger
            )
            time.sleep(0.5)
            
            # Wait for any floating elements to become non-blocking
            self.driver.execute_script(
                """
                var overlay = document.querySelector('[class*="fixed"][style*="top"]');
                if (overlay) {
                    overlay.style.pointerEvents = 'none';
                }
                """
            )
            time.sleep(0.3)
            
            # Retry click with fallback to ActionChains
            try:
                assign_trigger.click()
            except Exception as click_err:
                log.warning(f"Direct click failed, retrying with ActionChains: {click_err}")
                from selenium.webdriver.common.action_chains import ActionChains
                actions = ActionChains(self.driver)
                actions.move_to_element(assign_trigger).click().perform()
            
            time.sleep(1)
            self._handle_assign_modal(account_number)
            log.info(f"✅ Post assigned to {account_number}")
            return True
        except NoSuchElementException:
            log.warning("Assign button not found — post may already be assigned.")
            return True
        except Exception as exc:
            log.error(f"Failed to assign post: {exc}")
            return False

    def select_highest_priority(self, posts: list[DrummingPost]) -> Optional[DrummingPost]:
        """Return the post with the highest score."""
        if not posts:
            log.warning("No posts to prioritize.")
            return None
        best = posts[0]
        log.info(f"Selected highest-priority post: {best}")
        return best

    # ─────────────────────────────────────────────────────────
    # Card Parsing
    # ─────────────────────────────────────────────────────────

    def _parse_card(self, card: WebElement, idx: int) -> DrummingPost:
        """Extract all data from a single post card element."""

        def _text(css: str) -> str:
            try:
                return safe_strip(card.find_element(By.CSS_SELECTOR, css).text)
            except Exception:
                return ""

        def _attr(css: str, attr: str) -> str:
            try:
                el = card.find_element(By.CSS_SELECTOR, css)
                return safe_strip(el.get_attribute(attr) or "")
            except Exception:
                return ""

        # Title — full text is in h4's title attribute, display text is truncated
        title = _attr("h4[title]", "title") or _text("h4") or f"Post #{idx + 1}"

        # External link — try <a href> first, then button title attributes
        link = (
            _attr("a[href*='http']", "href")
            or self._extract_link_from_buttons(card)
        )

        # Score — the yellow number button
        raw_score = (
            _text("button[class*='bg-yellow']")
            or _text(".assignment-dropdown-container button")
        )
        score = self._parse_score(raw_score)

        # Status
        status = self._extract_status(card)

        # Platform — inferred from link
        platform = self._infer_platform(link)

        return DrummingPost(
            element=card,
            title=title,
            link=link,
            score=score,
            status=status,
            post_id=str(idx),
            platform=platform,
        )

    def _extract_link_from_buttons(self, card: WebElement) -> str:
        """
        Pearl27 shows the external URL in a button's title attribute,
        e.g. title="instagram.com/p/DXZBxG..."
        Reconstruct the full URL from it.
        """
        platform_domains = [
            "instagram.com", "reddit.com", "facebook.com",
            "youtube.com", "tiktok.com", "quora.com",
            "linkedin.com", "pinterest.com", "pinterest.ph",
        ]
        try:
            buttons = card.find_elements(By.CSS_SELECTOR, "button[title]")
            for btn in buttons:
                title_val = btn.get_attribute("title") or ""
                # Strip common prefixes from button labels
                title_val = title_val.strip()
                if title_val.lower().startswith(("open ", "visit ", "view ")):
                    title_val = title_val.split(" ", 1)[1]  # Remove first word
                
                for domain in platform_domains:
                    if domain in title_val.lower():
                        if title_val.startswith("http"):
                            return title_val.strip()
                        return f"https://{title_val.strip()}"
        except Exception:
            pass
        return ""

    def _extract_status(self, card: WebElement) -> str:
        """Extract the post status from status badge buttons."""
        known_statuses = ["Not Ready", "Draft Ready", "Approved", "Complete"]
        try:
            buttons = card.find_elements(By.CSS_SELECTOR, "button")
            for btn in buttons:
                text = safe_strip(btn.text)
                for status in known_statuses:
                    if status.lower() == text.lower():
                        return status
                    if status.lower() in text.lower():
                        return status
        except Exception:
            pass
        return "Unknown"

    # ─────────────────────────────────────────────────────────
    # Static helpers
    # ─────────────────────────────────────────────────────────

    @staticmethod
    def _parse_score(raw: str) -> float:
        match = re.search(r"[\d.]+", raw)
        return float(match.group()) if match else 0.0

    @staticmethod
    def _infer_platform(url: str) -> str:
        if not url:
            return "Unknown"
        url_lower = url.lower()
        platform_map = {
            "instagram.com": "Instagram",
            "reddit.com":    "Reddit",
            "facebook.com":  "Facebook",
            "youtube.com":   "YouTube",
            "tiktok.com":    "TikTok",
            "quora.com":     "Quora",
            "linkedin.com":  "LinkedIn",
            "pinterest.com": "Pinterest",
            "pinterest.ph":  "Pinterest",
        }
        for domain, name in platform_map.items():
            if domain in url_lower:
                return name
        return "Blog/Web"

    @staticmethod
    def _is_eligible(post: DrummingPost, account_number: str) -> bool:
        """Eligible = not already Complete."""
        if "complete" in post.status.lower():
            return False
        return True

    # ─────────────────────────────────────────────────────────
    # Assignment modal
    # ─────────────────────────────────────────────────────────

    def _handle_assign_modal(self, account_number: str) -> None:
        time.sleep(1)
        try:
            from selenium.webdriver.support.ui import Select
            select_el = self.find(
                By.CSS_SELECTOR, "select.account-select, select[name='account']", timeout=3
            )
            Select(select_el).select_by_visible_text(account_number)
        except Exception:
            pass

        try:
            input_el = self.find(
                By.CSS_SELECTOR, "input[placeholder*='account']", timeout=3
            )
            input_el.clear()
            input_el.send_keys(account_number)
        except Exception:
            pass

        try:
            self.click(
                By.CSS_SELECTOR, "button.confirm, button[type='submit'], .modal-confirm", timeout=5
            )
        except Exception:
            pass 