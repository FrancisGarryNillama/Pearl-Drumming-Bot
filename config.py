"""
config.py
=========
Central configuration module. Loads all environment variables
from .env and exposes them as typed attributes.
All secrets are masked in log output via __repr__.
"""

import os
from dataclasses import dataclass, field
from pathlib import Path
from dotenv import load_dotenv

# Load .env from project root
_PROJECT_ROOT = Path(__file__).parent
load_dotenv(_PROJECT_ROOT / ".env")


def _require(key: str) -> str:
    """Raise a clear error if a required env variable is missing."""
    value = os.getenv(key)
    if not value:
        raise EnvironmentError(
            f"Required environment variable '{key}' is not set. "
            f"Check your .env file."
        )
    return value


def _optional(key: str, default: str = "") -> str:
    return os.getenv(key, default)


# ─────────────────────────────────────────────
# Platform
# ─────────────────────────────────────────────
@dataclass
class PlatformConfig:
    url: str = field(default_factory=lambda: _require("PLATFORM_URL"))
    username: str = field(default_factory=lambda: _require("PLATFORM_USERNAME"))
    password: str = field(default_factory=lambda: _require("PLATFORM_PASSWORD"))
    account_number: str = field(default_factory=lambda: _optional("ACCOUNT_NUMBER", "PH1037"))
    drummer_name: str = field(default_factory=lambda: _optional("DRUMMER_NAME", "Garry"))
    site: str = "PH"

    def __repr__(self) -> str:
        return (
            f"PlatformConfig(url={self.url!r}, "
            f"username=***MASKED***, password=***MASKED***, "
            f"account={self.account_number!r})"
        )


# ─────────────────────────────────────────────
# LLM
# ─────────────────────────────────────────────
@dataclass
class LLMConfig:
    api_key: str = field(default_factory=lambda: _require("LLM_API_KEY"))
    model: str = field(default_factory=lambda: _optional("LLM_MODEL", "claude-3-5-sonnet-20241022"))
    base_url: str = field(
        default_factory=lambda: _optional(
            "LLM_BASE_URL", "https://api.anthropic.com/v1/messages"
        )
    )
    max_tokens: int = 1024
    temperature: float = 0.7

    def __repr__(self) -> str:
        return (
            f"LLMConfig(model={self.model!r}, "
            f"base_url={self.base_url!r}, api_key=***MASKED***)"
        )


# ─────────────────────────────────────────────
# Google Sheets
# ─────────────────────────────────────────────
@dataclass
class SheetsConfig:
    service_account_json: str = field(
        default_factory=lambda: _optional(
            "GOOGLE_SERVICE_ACCOUNT_JSON", "credentials/service_account.json"
        )
    )
    sheet_id: str = field(default_factory=lambda: _require("GOOGLE_SHEET_ID"))
    sheet_name: str = field(default_factory=lambda: _optional("GOOGLE_SHEET_NAME", "Sheet1"))
    sheet_url: str = field(default_factory=lambda: _optional("GOOGLE_SHEET_URL", ""))


# ─────────────────────────────────────────────
# WebDriver
# ─────────────────────────────────────────────
@dataclass
class WebDriverConfig:
    headless: bool = field(
        default_factory=lambda: _optional("HEADLESS", "false").lower() == "true"
    )
    timeout: int = field(
        default_factory=lambda: int(_optional("BROWSER_TIMEOUT", "30"))
    )
    implicit_wait: int = field(
        default_factory=lambda: int(_optional("IMPLICIT_WAIT", "10"))
    )
    page_load_timeout: int = field(
        default_factory=lambda: int(_optional("PAGE_LOAD_TIMEOUT", "60"))
    )


# ─────────────────────────────────────────────
# Retry / Resilience
# ─────────────────────────────────────────────
@dataclass
class RetryConfig:
    max_retries: int = field(
        default_factory=lambda: int(_optional("MAX_RETRIES", "3"))
    )
    retry_delay: float = field(
        default_factory=lambda: float(_optional("RETRY_DELAY", "2"))
    )


# ─────────────────────────────────────────────
# Logging
# ─────────────────────────────────────────────
@dataclass
class LogConfig:
    level: str = field(default_factory=lambda: _optional("LOG_LEVEL", "INFO"))
    log_file: str = field(
        default_factory=lambda: _optional("LOG_FILE", "logs/automation.log")
    )


# ─────────────────────────────────────────────
# Root Config (singleton-style)
# ─────────────────────────────────────────────
@dataclass
class AppConfig:
    platform: PlatformConfig = field(default_factory=PlatformConfig)
    llm: LLMConfig = field(default_factory=LLMConfig)
    sheets: SheetsConfig = field(default_factory=SheetsConfig)
    webdriver: WebDriverConfig = field(default_factory=WebDriverConfig)
    retry: RetryConfig = field(default_factory=RetryConfig)
    logging: LogConfig = field(default_factory=LogConfig)

    # Business constants
    SKIP_KEYWORD: str = "lifewood"
    FUZZY_MATCH_THRESHOLD: int = 85
    STATUS_FLOW: list = field(
        default_factory=lambda: ["Not Ready", "Draft Ready", "Approved", "Complete"]
    )
    SLANG_OPENERS: list = field(
        default_factory=lambda: [
            "Honestly",
            "Real talk",
            "No cap",
            "Lowkey",
            "Fr though",
            "Deadass",
            "Ngl",
        ]
    )


# Module-level singleton — import this everywhere
config = AppConfig()