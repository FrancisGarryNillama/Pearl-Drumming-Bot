"""
main.py
=======
Pearl27 Automation — Orchestrator Entry Point

Runs the full task lifecycle:
  1. Login
  2. Task assignment
  3. Content prioritization
  4. External scraping + keyword filter
  5. LLM comment generation
  6. Post reply
  7. Status workflow
  8. Google Sheets logging

Usage:
    python main.py
    python main.py --headless
    python main.py --dry-run     (skip posting/sheets for testing)
"""

import argparse
import sys
import time
import traceback
from pathlib import Path

# ── WebDriver ────────────────────────────────────────────────
from selenium import webdriver
from selenium.webdriver.chrome.options import Options as ChromeOptions
from selenium.webdriver.chrome.service import Service as ChromeService
from webdriver_manager.chrome import ChromeDriverManager

# ── Project modules ──────────────────────────────────────────
from config import AppConfig, config as default_config
from pages.login_page import LoginPage
from pages.dashboard_page import DashboardPage, DrummingPost
from pages.post_page import PostPage
from services.scraper import ExternalScraper, ScrapedContent
from services.llm_service import LLMService
from services.sheets_service import SheetsService
from utils.logger import setup_root_logger, get_logger

log = get_logger("pearl27.main")

# Max posts to process per run (set to 1 for single-post runs)
MAX_POSTS_PER_RUN = 1


# ─────────────────────────────────────────────────────────────
# Driver Factory
# ─────────────────────────────────────────────────────────────

def build_driver(cfg: AppConfig) -> webdriver.Chrome:
    """
    Initialise and return a configured Chrome WebDriver.
    Uses webdriver-manager to auto-download ChromeDriver.
    """
    options = ChromeOptions()

    if cfg.webdriver.headless:
        options.add_argument("--headless=new")
        log.info("Running in HEADLESS mode.")

    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--disable-gpu")
    options.add_argument("--window-size=1920,1080")
    options.add_argument("--disable-blink-features=AutomationControlled")
    options.add_experimental_option("excludeSwitches", ["enable-automation"])
    options.add_experimental_option("useAutomationExtension", False)

    # Suppress "Chrome is being controlled by automated software" banner
    options.add_argument("--disable-infobars")

    service = ChromeService(ChromeDriverManager().install())
    driver  = webdriver.Chrome(service=service, options=options)

    driver.implicitly_wait(cfg.webdriver.implicit_wait)
    driver.set_page_load_timeout(cfg.webdriver.page_load_timeout)

    # Anti-detection: remove webdriver property
    driver.execute_cdp_cmd(
        "Page.addScriptToEvaluateOnNewDocument",
        {"source": "Object.defineProperty(navigator, 'webdriver', {get: () => undefined})"}
    )

    log.info("✅ Chrome WebDriver initialised.")
    return driver


# ─────────────────────────────────────────────────────────────
# Orchestrator
# ─────────────────────────────────────────────────────────────

class Pearl27Orchestrator:
    """
    Coordinates the full automation workflow for Pearl27.
    Each phase is a separate method for clarity and testability.
    """

    def __init__(self, cfg: AppConfig, dry_run: bool = False):
        self.cfg     = cfg
        self.dry_run = dry_run
        self.driver: webdriver.Chrome | None = None

        # Shared services (initialised in setup())
        self.login_page:   LoginPage | None    = None
        self.dashboard:    DashboardPage | None = None
        self.post_page:    PostPage | None      = None
        self.scraper:      ExternalScraper | None = None
        self.llm:          LLMService | None    = None
        self.sheets:       SheetsService | None = None

        # Run-state tracking
        self.processed_count = 0

    # ─────────────────────────────────────────────────────────
    # Lifecycle
    # ─────────────────────────────────────────────────────────

    def setup(self) -> None:
        """Initialise driver and service instances."""
        log.info("=" * 60)
        log.info("Pearl27 Automation — Starting up")
        log.info("=" * 60)

        self.driver = build_driver(self.cfg)

        t = self.cfg.webdriver.timeout
        self.login_page = LoginPage(self.driver, timeout=t)
        self.dashboard  = DashboardPage(self.driver, timeout=t)
        self.post_page  = PostPage(self.driver, timeout=t)
        self.scraper    = ExternalScraper(driver=self.driver, timeout=t)
        self.llm        = LLMService(self.cfg.llm, self.cfg.SLANG_OPENERS)

        self.sheets = SheetsService(self.cfg.sheets, self.cfg.platform)
        if not self.dry_run:
            connected = self.sheets.connect()
            if connected:
                self.sheets.verify_column_map()

    def teardown(self) -> None:
        """Clean up resources."""
        if self.driver:
            self.driver.quit()
            log.info("WebDriver closed.")
        log.info(
            f"Run complete. Posts processed: {self.processed_count}"
        )

    # ─────────────────────────────────────────────────────────
    # Phase 1: Login
    # ─────────────────────────────────────────────────────────

    def phase_login(self) -> bool:
        """Authenticate with the Pearl27 platform."""
        log.info("── Phase 1: Login ──")
        success = self.login_page.login(
            url=self.cfg.platform.url,
            username=self.cfg.platform.username,
            password=self.cfg.platform.password,
        )
        if not success:
            log.error("Login failed. Aborting.")
        return success

    # ─────────────────────────────────────────────────────────
    # Phase 2: Task Discovery & Assignment
    # ─────────────────────────────────────────────────────────

    def phase_get_posts(self) -> list[DrummingPost]:
        """Find and assign unassigned posts to this account."""
        log.info("── Phase 2: Task Discovery & Assignment ──")
        posts = self.dashboard.get_unassigned_posts(self.cfg.platform.account_number)

        if not posts:
            log.warning("No eligible posts found.")
            return []

        log.info(f"Found {len(posts)} eligible post(s). Assigning …")
        for post in posts[:MAX_POSTS_PER_RUN]:
            if not self.dry_run:
                self.dashboard.assign_post(post, self.cfg.platform.account_number)

        return posts[:MAX_POSTS_PER_RUN]

    # ─────────────────────────────────────────────────────────
    # Phase 3: Prioritisation
    # ─────────────────────────────────────────────────────────

    def phase_prioritise(self, posts: list[DrummingPost]) -> DrummingPost | None:
        """Select the highest-scoring post."""
        log.info("── Phase 3: Prioritisation ──")
        return self.dashboard.select_highest_priority(posts)

    # ─────────────────────────────────────────────────────────
    # Phase 4 & 5: Scraping + Keyword Filter
    # ─────────────────────────────────────────────────────────

    def phase_scrape(self, post: DrummingPost) -> ScrapedContent | None:
        """
        Open the external link, scrape content,
        and apply the Lifewood skip filter.
        """
        log.info("── Phase 4 & 5: Scraping + Keyword Filter ──")

        # Navigate to the post detail to get the external link
        self.driver.get(post.link or self.cfg.platform.url)
        time.sleep(2)
        external_url = self.post_page.get_external_link() or post.link

        if not external_url:
            log.warning("No external URL found on post detail page.")
            return None

        log.info(f"External URL: {external_url}")
        scraped = self.scraper.scrape(external_url)

        # Apply skip filter
        if scraped.has_skip_keyword(
            self.cfg.SKIP_KEYWORD,
            self.cfg.FUZZY_MATCH_THRESHOLD
        ):
            log.warning(
                f"⚠️  Skip keyword '{self.cfg.SKIP_KEYWORD}' detected "
                f"in comments — skipping this post."
            )
            return None

        return scraped

    # ─────────────────────────────────────────────────────────
    # Phase 6: LLM Generation
    # ─────────────────────────────────────────────────────────

    def phase_generate(self, scraped: ScrapedContent, post_url: str) -> str | None:
        """Generate a Pearl27-style comment via LLM."""
        log.info("── Phase 6: LLM Generation ──")

        comment = self.llm.generate(scraped, post_url)
        if not comment:
            log.error("LLM generation failed.")
            return None

        log.info(f"Generated comment ({comment.mode.name}):\n{comment.text}\n")
        return comment.text

    # ─────────────────────────────────────────────────────────
    # Phase 7: Post Reply
    # ─────────────────────────────────────────────────────────

    def phase_post_reply(self, post: DrummingPost, comment_text: str) -> bool:
        """Submit the generated comment on the platform post."""
        log.info("── Phase 7: Post Reply ──")

        if self.dry_run:
            log.info("[DRY RUN] Would post comment:\n" + comment_text)
            return True

        # Navigate back to the platform post page
        if post.link:
            self.driver.get(post.link)
            time.sleep(2)

        return self.post_page.submit_comment(comment_text)

    # ─────────────────────────────────────────────────────────
    # Phase 8: Status Workflow
    # ─────────────────────────────────────────────────────────

    def phase_advance_status(self) -> bool:
        """Advance the post through all status transitions."""
        log.info("── Phase 8: Status Workflow ──")

        if self.dry_run:
            log.info(f"[DRY RUN] Would advance status through: {self.cfg.STATUS_FLOW}")
            return True

        return self.post_page.advance_status(self.cfg.STATUS_FLOW)

    # ─────────────────────────────────────────────────────────
    # Phase 9: Google Sheets Logging
    # ─────────────────────────────────────────────────────────

    def phase_log_to_sheets(self, post: DrummingPost, platform: str) -> bool:
        """Log task completion to the Google Sheets tracker."""
        log.info("── Phase 9: Google Sheets Logging ──")

        if self.dry_run:
            log.info(
                f"[DRY RUN] Would log to sheets: "
                f"platform={platform}, url={post.link}"
            )
            return True

        return self.sheets.log_task_completion(
            post_url=post.link,
            platform=platform,
            num_posts=1,
        )

    # ─────────────────────────────────────────────────────────
    # Full Run
    # ─────────────────────────────────────────────────────────

    def run(self) -> bool:
        """Execute the complete automation workflow."""
        try:
            # Phase 1: Login
            if not self.phase_login():
                return False

            # Phase 2: Task discovery
            posts = self.phase_get_posts()
            if not posts:
                log.warning("No posts to process. Exiting cleanly.")
                return True

            for post in posts:
                log.info(f"\n{'─'*50}")
                log.info(f"Processing post: {post.title!r}")
                log.info(f"{'─'*50}\n")

                # Phase 3: Prioritise (already sorted, just log)
                best_post = self.phase_prioritise([post])
                if not best_post:
                    continue

                # Phase 4 & 5: Scrape + filter
                scraped = self.phase_scrape(best_post)
                if scraped is None:
                    log.info("Post skipped (keyword filter or scrape failure).")
                    continue

                # Phase 6: LLM generation
                external_url = scraped.url or best_post.link
                comment_text = self.phase_generate(scraped, external_url)
                if not comment_text:
                    log.error("Skipping post — no comment generated.")
                    continue

                # Phase 7: Post reply
                posted = self.phase_post_reply(best_post, comment_text)
                if not posted:
                    log.error("Failed to post comment. Continuing to status update.")

                # Phase 8: Status workflow
                self.phase_advance_status()

                # Phase 9: Sheets logging
                platform = scraped.platform or best_post.platform or "Unknown"
                self.phase_log_to_sheets(best_post, platform)

                self.processed_count += 1
                log.info(f"✅ Post #{self.processed_count} complete.\n")

            return True

        except KeyboardInterrupt:
            log.warning("Run interrupted by user.")
            return False
        except Exception as exc:
            log.error(f"Unhandled exception in run: {exc}")
            log.debug(traceback.format_exc())
            if self.driver:
                self.driver.save_screenshot("logs/error_screenshot.png")
            return False


# ─────────────────────────────────────────────────────────────
# CLI Entry Point
# ─────────────────────────────────────────────────────────────

def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Pearl27 Drumming Platform Automation"
    )
    parser.add_argument(
        "--headless",
        action="store_true",
        help="Run Chrome in headless mode (no visible browser window)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Run all phases but skip actual posting and sheets updates",
    )
    parser.add_argument(
        "--log-level",
        default=None,
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        help="Override log level",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()

    # Load config
    cfg = default_config

    # CLI overrides
    if args.headless:
        cfg.webdriver.headless = True
    if args.log_level:
        cfg.logging.level = args.log_level

    # Setup logging
    log_dir = Path(cfg.logging.log_file).parent
    log_dir.mkdir(parents=True, exist_ok=True)
    setup_root_logger(level=cfg.logging.level, log_file=cfg.logging.log_file)

    log.info(f"Config: {cfg.platform}")
    log.info(f"Headless: {cfg.webdriver.headless} | Dry-run: {args.dry_run}")

    orchestrator = Pearl27Orchestrator(cfg, dry_run=args.dry_run)

    try:
        orchestrator.setup()
        success = orchestrator.run()
    finally:
        orchestrator.teardown()

    return 0 if success else 1


if __name__ == "__main__":
    sys.exit(main())