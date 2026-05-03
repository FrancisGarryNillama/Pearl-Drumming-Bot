"""
services/scraper.py
===================
Scrapes external URLs (Quora, Reddit, blogs, etc.) to extract:
  - Post description / main body
  - Context metadata
  - Comments section

Uses Selenium (JavaScript-heavy pages) with BeautifulSoup fallback.
"""

import time
from dataclasses import dataclass, field
from typing import Optional

import requests
from bs4 import BeautifulSoup
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.common.exceptions import TimeoutException

from utils.logger import get_logger
from utils.helpers import safe_strip, truncate, contains_keyword_fuzzy, retry

log = get_logger(__name__)

# ── Request headers for direct HTTP scraping ──────────────────
_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/122.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "en-US,en;q=0.9",
}


@dataclass
class ScrapedContent:
    """Container for everything extracted from an external page."""
    url: str = ""
    title: str = ""
    description: str = ""
    context: str = ""
    comments: list[str] = field(default_factory=list)
    raw_html: str = ""
    platform: str = ""

    @property
    def full_text(self) -> str:
        """Combined text for LLM context."""
        parts = [
            f"Title: {self.title}",
            f"Description: {self.description}",
            f"Context: {self.context}",
        ]
        if self.comments:
            parts.append("Comments:\n" + "\n".join(f"- {c}" for c in self.comments[:15]))
        return "\n\n".join(filter(None, parts))

    def has_skip_keyword(self, keyword: str = "lifewood", threshold: int = 85) -> bool:
        """Return True if any comment contains the skip keyword (fuzzy)."""
        for comment in self.comments:
            if contains_keyword_fuzzy(comment, keyword, threshold):
                log.info(f"Skip keyword '{keyword}' found in comment: {comment[:80]!r}")
                return True
        return False


class ExternalScraper:
    """
    Scrapes external post pages.

    Tries fast HTTP request first; falls back to Selenium
    for JavaScript-rendered pages.
    """

    def __init__(self, driver: Optional[webdriver.Chrome] = None, timeout: int = 30):
        self.driver = driver
        self.timeout = timeout

    # ─────────────────────────────────────────────────────────
    # Public API
    # ─────────────────────────────────────────────────────────

    @retry(max_attempts=3, delay=2.0)
    def scrape(self, url: str) -> ScrapedContent:
        """
        Scrape an external URL and return structured content.

        Tries HTTP first, then Selenium if needed.
        """
        if not url:
            log.warning("Empty URL passed to scraper.")
            return ScrapedContent(url=url)

        # Clean and validate the URL
        url = self._clean_url(url)
        if not url or not self._is_valid_url(url):
            log.error(f"Invalid or malformed URL: {url!r}")
            return ScrapedContent(url=url)

        log.info(f"Scraping: {url}")
        platform = self._detect_platform(url)

        # Quora blocks simple HTTP — always use Selenium
        if "quora.com" in url.lower() and self.driver:
            content = self._scrape_with_selenium(url)
        else:
            content = self._scrape_with_http(url)
            if not content.description and self.driver:
                log.info("HTTP scrape yielded no content — trying Selenium …")
                content = self._scrape_with_selenium(url)

        content.platform = platform
        log.info(
            f"Scraped '{content.title[:60]}' — "
            f"{len(content.comments)} comment(s)"
        )
        return content

    # ─────────────────────────────────────────────────────────
    # HTTP Scraping
    # ─────────────────────────────────────────────────────────

    def _scrape_with_http(self, url: str) -> ScrapedContent:
        """Direct HTTP request + BeautifulSoup parsing."""
        try:
            resp = requests.get(url, headers=_HEADERS, timeout=self.timeout)
            resp.raise_for_status()
            soup = BeautifulSoup(resp.text, "lxml")
            return self._parse_soup(url, soup, resp.text)
        except Exception as exc:
            log.warning(f"HTTP scrape failed for {url}: {exc}")
            return ScrapedContent(url=url)

    def _parse_soup(self, url: str, soup: BeautifulSoup, raw_html: str) -> ScrapedContent:
        """Generic BeautifulSoup parser — works for most blog / article pages."""
        # Title
        title = safe_strip(
            (soup.find("h1") or soup.find("title") or soup.find("h2") or "").get_text()
            if not isinstance((soup.find("h1") or ""), str) else ""
        )
        if not title and soup.title:
            title = soup.title.string or ""
        title = safe_strip(title)

        # Main description / body text
        # Priority: article > main > .post-content > p tags
        body_el = (
            soup.find("article")
            or soup.find("main")
            or soup.find(class_=["post-content", "entry-content", "article-body", "content"])
        )
        if body_el:
            description = safe_strip(body_el.get_text(separator=" ", strip=True))
        else:
            paragraphs = soup.find_all("p")
            description = " ".join(p.get_text(strip=True) for p in paragraphs[:10])

        description = truncate(description, 3000)

        # Context: meta description / og:description
        context = ""
        for meta_attr in [("name", "description"), ("property", "og:description")]:
            meta = soup.find("meta", {meta_attr[0]: meta_attr[1]})
            if meta:
                context = safe_strip(meta.get("content", ""))
                break

        # Comments
        comments = self._extract_comments_from_soup(soup)

        return ScrapedContent(
            url=url,
            title=title,
            description=description,
            context=context,
            comments=comments,
            raw_html=raw_html[:5000],
        )

    @staticmethod
    def _extract_comments_from_soup(soup: BeautifulSoup) -> list[str]:
        """Extract comments from common comment structures."""
        comments: list[str] = []

        # Common comment container selectors
        selectors = [
            ".comment-text", ".comment-body", ".comment-content",
            "[class*='comment']", ".reply-text", ".user-comment",
            ".answer", ".response",
        ]
        for sel in selectors:
            els = soup.select(sel)
            for el in els[:30]:
                text = safe_strip(el.get_text(separator=" ", strip=True))
                if text and len(text) > 10:
                    comments.append(truncate(text, 500))

        return comments[:30]

    # ─────────────────────────────────────────────────────────
    # Selenium Scraping
    # ─────────────────────────────────────────────────────────

    def _scrape_with_selenium(self, url: str) -> ScrapedContent:
        """Use the existing Selenium driver to scrape JS-heavy pages."""
        if not self.driver:
            log.error("Selenium driver not available.")
            return ScrapedContent(url=url)

        original_url = self.driver.current_url
        try:
            self.driver.execute_script(f"window.open('{url}', '_blank');")
            time.sleep(1)
            self.driver.switch_to.window(self.driver.window_handles[-1])

            # Wait for page load
            from selenium.webdriver.support.ui import WebDriverWait
            from selenium.webdriver.support import expected_conditions as EC
            WebDriverWait(self.driver, self.timeout).until(
                lambda d: d.execute_script("return document.readyState") == "complete"
            )
            time.sleep(2)  # Extra wait for SPA content

            # Scroll to load lazy content
            self.driver.execute_script("window.scrollTo(0, document.body.scrollHeight / 2);")
            time.sleep(1)

            html = self.driver.page_source
            soup = BeautifulSoup(html, "lxml")

            content = self._parse_soup(url, soup, html)

            # Platform-specific enhancements
            if "quora.com" in url.lower():
                content = self._enhance_quora(content, soup)

        except Exception as exc:
            log.error(f"Selenium scrape failed for {url}: {exc}")
            content = ScrapedContent(url=url)
        finally:
            # Close opened tab and return to original
            try:
                if len(self.driver.window_handles) > 1:
                    self.driver.close()
                    self.driver.switch_to.window(self.driver.window_handles[-1])
            except Exception:
                pass

        return content

    @staticmethod
    def _enhance_quora(content: ScrapedContent, soup: BeautifulSoup) -> ScrapedContent:
        """Apply Quora-specific extraction improvements."""
        # Quora answers are in .q-box divs
        answers = soup.select(".q-box, .qu-dynamicFontSize, [class*='answer']")
        answer_texts = [
            a.get_text(separator=" ", strip=True)
            for a in answers[:5]
            if len(a.get_text(strip=True)) > 50
        ]
        if answer_texts:
            content.description = truncate(answer_texts[0], 3000)
            content.comments = [truncate(t, 500) for t in answer_texts[1:]]

        return content

    # ─────────────────────────────────────────────────────────
    # Platform Detection
    # ─────────────────────────────────────────────────────────

    @staticmethod
    def _detect_platform(url: str) -> str:
        """Identify the platform from the URL."""
        url_lower = url.lower()
        platform_map = {
            "quora.com":   "Quora",
            "reddit.com":  "Reddit",
            "facebook.com":"Facebook",
            "twitter.com": "Twitter",
            "x.com":       "X (Twitter)",
            "instagram.com":"Instagram",
            "linkedin.com":"LinkedIn",
            "medium.com":  "Medium",
            "youtube.com": "YouTube",
        }
        for domain, name in platform_map.items():
            if domain in url_lower:
                return name
        return "Blog/Web"

    def _clean_url(self, url: str) -> str:
        """
        Clean and normalize URL by removing common prefixes/suffixes.
        E.g., 'Open www.linkedin.com/posts/...' -> 'https://www.linkedin.com/posts/...'
        """
        url = url.strip()
        
        # Remove common button label prefixes
        prefixes_to_strip = ["open ", "visit ", "view ", "check ", "read ", "see "]
        for prefix in prefixes_to_strip:
            if url.lower().startswith(prefix):
                url = url[len(prefix):].strip()
        
        # Ensure https:// prefix
        if not url.startswith(("http://", "https://")):
            url = f"https://{url}"
        
        # Remove trailing whitespace
        url = url.rstrip()
        
        return url

    def _is_valid_url(self, url: str) -> bool:
        """Check if URL is valid and accessible."""
        # Must start with http/https
        if not url.startswith(("http://", "https://")):
            return False
        
        # Must have at least a domain
        try:
            from urllib.parse import urlparse
            parsed = urlparse(url)
            # Must have a netloc (domain part)
            return bool(parsed.netloc)
        except Exception:
            return False