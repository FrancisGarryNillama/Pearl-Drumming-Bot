"""
services/social_poster.py
==========================
Routes comment posting to the correct social media platform page object.

Usage:
    poster = SocialPoster(driver, social_cfg)
    success = poster.post(url="https://reddit.com/r/drums/...", comment="...")
"""

from typing import Optional
from urllib.parse import urlparse

from selenium import webdriver

from config import SocialCredentialsConfig
from pages.social.reddit_page import RedditPage
from pages.social.quora_page import QuoraPage
from pages.social.linkedin_page import LinkedInPage
from pages.social.facebook_page import FacebookPage
from pages.social.youtube_page import YouTubePage
from pages.social.tiktok_page import TikTokPage
from pages.social.instagram_page import InstagramPage
from pages.social.pinterest_page import PinterestPage
from pages.social.base_social_page import BaseSocialPage
from utils.logger import get_logger

log = get_logger(__name__)

# Maps domain keywords → (page class, username_key, password_key)
_PLATFORM_REGISTRY = {
    "reddit.com":    ("reddit",    RedditPage),
    "quora.com":     ("quora",     QuoraPage),
    "linkedin.com":  ("linkedin",  LinkedInPage),
    "facebook.com":  ("facebook",  FacebookPage),
    "fb.com":        ("facebook",  FacebookPage),
    "youtube.com":   ("youtube",   YouTubePage),
    "youtu.be":      ("youtube",   YouTubePage),
    "tiktok.com":    ("tiktok",    TikTokPage),
    "instagram.com": ("instagram", InstagramPage),
    "pinterest.com": ("pinterest", PinterestPage),
    "pinterest.ph":  ("pinterest", PinterestPage),
}


class SocialPoster:
    """
    Detects the platform from a URL, ensures the correct
    social account is logged in, and posts the comment.

    Login state is cached per platform — each platform only
    logs in once per run.
    """

    def __init__(self, driver: webdriver.Chrome, social_cfg: SocialCredentialsConfig, timeout: int = 30):
        self.driver = driver
        self.cfg = social_cfg
        self.timeout = timeout
        # Cache of platform_key -> page object (logged-in instances)
        self._pages: dict[str, BaseSocialPage] = {}

    # ─────────────────────────────────────────────────────────
    # Public API
    # ─────────────────────────────────────────────────────────

    def post(self, url: str, comment_text: str) -> bool:
        """
        Post a comment on the given URL.

        Args:
            url:          Full URL of the social media post
            comment_text: The comment to post

        Returns:
            True if comment was posted successfully.
        """
        platform_key, page_class = self._detect_platform(url)

        if platform_key is None:
            log.warning(f"[SocialPoster] Unsupported platform for URL: {url}")
            return False

        # Get or create the page object
        page = self._get_or_create_page(platform_key, page_class)
        if page is None:
            return False

        # Get credentials
        username, password = self._get_credentials(platform_key)
        if not username or not password:
            log.error(
                f"[SocialPoster] No credentials configured for '{platform_key}'. "
                f"Check your .env file."
            )
            return False

        # Ensure we're logged in
        if not page.ensure_logged_in(username, password):
            log.error(f"[SocialPoster] Login failed for {platform_key}.")
            return False

        # Post the comment
        log.info(f"[SocialPoster] Posting to {platform_key}: {url[:80]}")
        success = page.post_comment(url, comment_text)

        if success:
            log.info(f"[SocialPoster] ✅ Comment posted on {platform_key}.")
        else:
            log.error(f"[SocialPoster] ❌ Failed to post comment on {platform_key}.")

        return success

    def detect_platform_name(self, url: str) -> str:
        """Return the human-readable platform name for a URL."""
        key, page_class = self._detect_platform(url)
        if page_class:
            return page_class.PLATFORM_NAME
        return "Unknown"

    # ─────────────────────────────────────────────────────────
    # Internal helpers
    # ─────────────────────────────────────────────────────────

    def _detect_platform(self, url: str) -> tuple[Optional[str], Optional[type]]:
        """Return (platform_key, page_class) for a URL, or (None, None)."""
        if not url:
            return None, None
        try:
            hostname = urlparse(url).hostname or ""
        except Exception:
            hostname = url.lower()

        for domain, (key, cls) in _PLATFORM_REGISTRY.items():
            if domain in hostname:
                return key, cls

        return None, None

    def _get_or_create_page(self, key: str, cls: type) -> Optional[BaseSocialPage]:
        """Return cached page object or create a new one."""
        if key not in self._pages:
            try:
                self._pages[key] = cls(self.driver, timeout=self.timeout)
            except Exception as exc:
                log.error(f"[SocialPoster] Failed to create page for {key}: {exc}")
                return None
        return self._pages[key]

    def _get_credentials(self, platform_key: str) -> tuple[str, str]:
        """Look up username and password for the given platform."""
        cfg = self.cfg
        mapping = {
            "reddit":    (cfg.reddit_username,    cfg.reddit_password),
            "quora":     (cfg.quora_email,         cfg.quora_password),
            "linkedin":  (cfg.linkedin_email,      cfg.linkedin_password),
            "facebook":  (cfg.facebook_email,      cfg.facebook_password),
            "youtube":   (cfg.youtube_email,       cfg.youtube_password),
            "tiktok":    (cfg.tiktok_username,     cfg.tiktok_password),
            "instagram": (cfg.instagram_username,  cfg.instagram_password),
            "pinterest": (cfg.pinterest_email,     cfg.pinterest_password),
        }
        return mapping.get(platform_key, ("", ""))