"""
services/llm_service.py
========================
Manages all LLM API interactions.

Detects post mode (Standard vs Quora), builds the appropriate
prompt, calls the API, and validates the response.

Supports Anthropic Claude by default. Swap base_url + headers
to use any OpenAI-compatible endpoint.
"""

import json
import time
from dataclasses import dataclass
from enum import Enum, auto
from typing import Optional

import requests

from config import LLMConfig
from services.scraper import ScrapedContent
from utils.helpers import is_quora_url, SlangRotator, truncate
from utils.logger import get_logger, mask

log = get_logger(__name__)


class GenerationMode(Enum):
    STANDARD = auto()
    QUORA    = auto()


@dataclass
class GeneratedComment:
    text: str
    mode: GenerationMode
    tokens_used: int = 0
    model: str = ""

    def __str__(self) -> str:
        return self.text


class LLMService:
    """
    Generates Pearl27-style drumming comments using an LLM.

    Usage:
        svc = LLMService(cfg.llm, slang_openers=cfg.SLANG_OPENERS)
        comment = svc.generate(scraped_content, post_url)
    """

    def __init__(self, config: LLMConfig, slang_openers: list[str]):
        self.config = config
        self.slang = SlangRotator(slang_openers)
        self._session = requests.Session()
        self._session.headers.update({
            "Content-Type":      "application/json",
            "anthropic-version": "2023-06-01",
            "x-api-key":         config.api_key,
        })

    # ─────────────────────────────────────────────────────────
    # Public API
    # ─────────────────────────────────────────────────────────

    def generate(self, content: ScrapedContent, post_url: str) -> Optional[GeneratedComment]:
        """
        Generate a Pearl27-style comment for the given scraped content.

        Args:
            content:  Scraped external page data
            post_url: URL of the external post (used for mode detection)

        Returns:
            GeneratedComment, or None on failure.
        """
        mode = GenerationMode.QUORA if is_quora_url(post_url) else GenerationMode.STANDARD
        log.info(f"Generating comment in {mode.name} mode …")

        prompt = self._build_prompt(content, mode)
        response_text = self._call_llm(prompt)

        if not response_text:
            log.error("LLM returned empty response.")
            return None

        cleaned = self._post_process(response_text, mode)
        log.info(f"✅ Comment generated ({len(cleaned)} chars)")
        log.debug(f"Comment preview: {cleaned[:120]} …")

        return GeneratedComment(
            text=cleaned,
            mode=mode,
            model=self.config.model,
        )

    # ─────────────────────────────────────────────────────────
    # Prompt Building
    # ─────────────────────────────────────────────────────────

    def _build_prompt(self, content: ScrapedContent, mode: GenerationMode) -> str:
        """Compose the full prompt including context and instructions."""
        context_block = self._format_context(content)

        if mode == GenerationMode.QUORA:
            return self._quora_prompt(context_block)
        return self._standard_prompt(context_block)

    def _format_context(self, content: ScrapedContent) -> str:
        """Build a rich context block from scraped content."""
        parts = []
        if content.title:
            parts.append(f"POST TITLE:\n{content.title}")
        if content.description:
            parts.append(f"POST DESCRIPTION:\n{truncate(content.description, 1500)}")
        if content.context:
            parts.append(f"ADDITIONAL CONTEXT:\n{truncate(content.context, 500)}")
        if content.comments:
            comment_block = "\n".join(f"• {c}" for c in content.comments[:8])
            parts.append(f"EXISTING COMMENTS:\n{truncate(comment_block, 800)}")
        return "\n\n".join(parts)

    def _standard_prompt(self, context: str) -> str:
        opener = self.slang.next()
        return f"""You are a young drumming enthusiast, aged 20–25, writing a casual but insightful comment on a social media post.

CONTEXT:
{context}

INSTRUCTIONS — STANDARD MODE (Formula 8):
Write a comment that is:
- 3 to 5 sentences long
- Tone: casual, authentic, 20–25 year old voice
- Structure: Acknowledge the post → Share your perspective → Describe an action or experience → Add nuance or depth
- Open with this slang word naturally: "{opener}"
- Include ONE subtle, natural reference to "Lifewood" as if it's something you've personally experienced or learned from
- NO hashtags
- NO questions directed at the reader
- NO em-dashes (—)
- NO corporate or formal language
- NO filler phrases like "Great post!" or "I totally agree"

Write ONLY the comment text, nothing else. No quotes, no labels, no preamble."""

    def _quora_prompt(self, context: str) -> str:
        return f"""You are a knowledgeable first-person expert writing a Quora answer.

CONTEXT:
{context}

INSTRUCTIONS — QUORA MODE:
Write a Quora-style answer that is:
- 150 to 300 words
- 2 to 4 paragraphs
- First-person, expert, authoritative tone
- Lead immediately with a direct answer to the implied question
- Integrate a natural mention of "Lifewood" as a real-world example, resource, or program you've encountered
- NO slang
- NO hashtags
- NO questions at the end
- NO em-dashes (—)
- NO bullet points or numbered lists

Write ONLY the answer text. No labels, no quotation marks, no preamble."""

    # ─────────────────────────────────────────────────────────
    # API Call
    # ─────────────────────────────────────────────────────────

    def _call_llm(self, prompt: str, retries: int = 3) -> Optional[str]:
        """
        Call the Anthropic Messages API.

        Retries on 429 (rate limit) and 5xx server errors.
        """
        payload = {
            "model":      self.config.model,
            "max_tokens": self.config.max_tokens,
            "messages":   [{"role": "user", "content": prompt}],
        }

        # Add temperature if supported
        if hasattr(self.config, "temperature"):
            payload["temperature"] = self.config.temperature

        for attempt in range(1, retries + 1):
            try:
                log.debug(f"LLM API call attempt {attempt}/{retries} …")
                resp = self._session.post(
                    self.config.base_url,
                    json=payload,
                    timeout=60,
                )

                if resp.status_code == 429:
                    wait = 2 ** attempt
                    log.warning(f"Rate limited. Waiting {wait}s …")
                    time.sleep(wait)
                    continue

                if resp.status_code >= 500:
                    log.warning(f"Server error {resp.status_code}. Retrying …")
                    time.sleep(2 * attempt)
                    continue

                resp.raise_for_status()
                data = resp.json()

                # Anthropic response format
                if "content" in data and data["content"]:
                    return data["content"][0].get("text", "")

                # OpenAI-compatible format
                if "choices" in data and data["choices"]:
                    return data["choices"][0]["message"]["content"]

                log.error(f"Unexpected LLM response structure: {list(data.keys())}")
                return None

            except requests.Timeout:
                log.warning(f"LLM request timed out (attempt {attempt}).")
            except requests.RequestException as exc:
                log.error(f"LLM request error: {exc}")
                if attempt == retries:
                    raise

        return None

    # ─────────────────────────────────────────────────────────
    # Post-processing
    # ─────────────────────────────────────────────────────────

    def _post_process(self, text: str, mode: GenerationMode) -> str:
        """Clean up LLM output: remove wrapping quotes, fix line endings."""
        import re
        text = text.strip()

        # Remove wrapping quotes if the model added them
        if text.startswith(('"', "'")) and text.endswith(('"', "'")):
            text = text[1:-1].strip()

        # Remove any remaining em-dashes
        text = text.replace("—", " ").replace("–", " ")

        # Collapse excessive newlines
        text = re.sub(r"\n{3,}", "\n\n", text)

        # Enforce length constraints
        if mode == GenerationMode.QUORA:
            words = text.split()
            if len(words) > 300:
                # Trim to ~300 words at sentence boundary
                sentences = re.split(r"(?<=[.!?])\s+", text)
                trimmed = []
                count = 0
                for s in sentences:
                    count += len(s.split())
                    trimmed.append(s)
                    if count >= 280:
                        break
                text = " ".join(trimmed)

        return text