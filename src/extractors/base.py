"""Base extractor with hybrid 3-layer pipeline.

Pipeline:
1. Screenshot Capture (Playwright, runs on Linux/GH Actions)
2. Dual Extraction:
   - Code extraction (structured data from HTML/JSON)
   - AI Vision extraction (Gemini reads the screenshot)
3. Reconciliation (merge code + AI, flag disagreements)

Subclasses implement:
- code_extract(html) → partial dict (prices + what code can reliably get)
- get_extraction_prompt() → competitor-specific instructions for Vision AI
"""

from __future__ import annotations

import json
import logging
import os
from abc import ABC, abstractmethod
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from pydantic import BaseModel

logger = logging.getLogger(__name__)


class ExtractionError(Exception):
    """Raised when extraction fails after all attempts."""
    pass


class BaseExtractor(ABC):
    """Base class for competitor pricing extractors."""

    competitor: str
    display_name: str
    url: str
    schema_cls: type[BaseModel]

    async def fetch_html(self) -> str:
        """Fetch HTML from the pricing page using httpx."""
        import httpx

        headers = {
            "User-Agent": (
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/125.0.0.0 Safari/537.36"
            ),
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9",
        }

        async with httpx.AsyncClient(follow_redirects=True, timeout=30.0) as client:
            response = await client.get(self.url, headers=headers)
            response.raise_for_status()
            return response.text

    async def code_extract(self, html: str) -> dict[str, Any] | None:
        """Code-based extraction — returns partial result or None.

        Override in subclasses to extract prices and structured data
        that code can reliably parse. Returns None if not implemented.
        """
        return None

    def get_extraction_prompt(self) -> str:
        """Return competitor-specific prompt for Vision AI. Override in subclasses."""
        return ""

    async def extract(self) -> BaseModel:
        """Run the full 3-layer extraction pipeline."""
        from .screenshot import capture_screenshots
        from .vision import extract_from_screenshot
        from .reconcile import reconcile

        logger.info(f"Starting hybrid extraction for {self.display_name}")

        # Layer 1: Screenshot capture (may fail on macOS — that's OK)
        screenshots = await capture_screenshots(self.competitor)
        has_screenshots = screenshots is not None and len(screenshots) > 0

        # Layer 2a: Code extraction
        code_result = None
        html = None
        try:
            html = await self.fetch_html()
            code_result = await self.code_extract(html)
            if code_result:
                logger.info(f"Code extraction succeeded for {self.display_name}")
        except Exception as e:
            logger.warning(f"Code extraction failed for {self.display_name}: {e}")

        # Layer 2b: AI Vision extraction (if screenshot available)
        ai_result = None
        if has_screenshots:
            try:
                schema_json = json.dumps(self.schema_cls.model_json_schema(), indent=2)
                ai_result = await extract_from_screenshot(
                    screenshots[0], self.competitor, schema_json
                )
                logger.info(f"AI Vision extraction succeeded for {self.display_name}")
            except Exception as e:
                logger.warning(f"AI Vision extraction failed for {self.display_name}: {e}")
        else:
            # No screenshots — always try HTML-based AI for features
            # (code extraction only gets prices, AI gets the comparison table)
            logger.info(f"No screenshots for {self.display_name} — trying HTML-based AI")
            try:
                if html is None:
                    html = await self.fetch_html()
                ai_result = await self._ai_extract_from_html(html)
                logger.info(f"HTML-based AI extraction succeeded for {self.display_name}")
            except Exception as e:
                logger.warning(f"HTML-based AI extraction failed for {self.display_name}: {e}")

        # Layer 3: Reconciliation
        merged, warnings = reconcile(code_result, ai_result, self.competitor)

        for w in warnings:
            logger.warning(f"[{self.competitor}] {w}")

        # Validate against schema
        try:
            result = self.schema_cls.model_validate(merged)
            logger.info(
                f"Extraction succeeded for {self.display_name} "
                f"(method={merged.get('extraction_method', '?')}, "
                f"warnings={len(warnings)})"
            )
            return result
        except Exception as e:
            raise ExtractionError(
                f"Schema validation failed for {self.display_name}: {e}\n"
                f"Warnings: {warnings}"
            )

    async def _ai_extract_from_html(self, html: str) -> dict[str, Any]:
        """Fallback: AI extraction from HTML when screenshots unavailable.

        Used for local development/testing where Playwright can't run.
        """
        import re

        api_key = os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
        if not api_key:
            raise ExtractionError("No GEMINI_API_KEY set for AI fallback")

        import google.generativeai as genai

        genai.configure(api_key=api_key)

        cleaned_html = self._clean_html(html)
        schema_json = json.dumps(self.schema_cls.model_json_schema(), indent=2)

        prompt = f"""You are extracting pricing data from an HTML page.

{self.get_extraction_prompt()}

## CRITICAL RULES
- All prices in USD, per-unit, per-MONTH
- monthly_per_unit = month-to-month price (higher), annual_per_unit = annual price (lower)
- Extract EVERY feature from comparison tables
- Checkmark = available: true, Dash = available: false
- "Contact Sales" = is_custom_pricing: true, pricing: null
- NEVER invent data. If unclear, use null.

## JSON SCHEMA
```json
{schema_json}
```

## HTML
```html
{cleaned_html}
```

Return ONLY valid JSON.
"""

        model = genai.GenerativeModel("gemini-2.5-flash")
        response = await model.generate_content_async(
            prompt,
            generation_config=genai.GenerationConfig(
                temperature=0.0,
                response_mime_type="application/json",
            ),
        )

        result = self._parse_json_response(response.text)

        # Override metadata
        result["competitor"] = self.competitor
        result["display_name"] = self.display_name
        result["url"] = self.url
        result["extracted_at"] = datetime.now(timezone.utc).isoformat()
        result["extraction_method"] = "ai"
        result["data_version"] = 1

        return result

    def _clean_html(self, html: str, max_chars: int = 150000) -> str:
        """Strip non-content elements for AI processing."""
        import re
        from bs4 import BeautifulSoup

        soup = BeautifulSoup(html, "html.parser")

        for tag in soup.find_all(["script", "style", "svg", "img", "noscript",
                                   "iframe", "link", "meta", "head",
                                   "video", "audio", "canvas", "picture", "source"]):
            tag.decompose()

        for el in soup.find_all(attrs={"style": re.compile(r"display\s*:\s*none", re.I)}):
            el.decompose()

        for el in soup.find_all():
            attrs_to_remove = [k for k in el.attrs if k not in ["id", "href", "role", "data-cy"]]
            for attr in attrs_to_remove:
                del el[attr]

        body = soup.find("body") or soup
        text = str(body)

        if len(text) <= max_chars:
            return text

        text = body.get_text("\n", strip=True)
        text = re.sub(r"\n{3,}", "\n\n", text)
        return text[:max_chars]

    def _parse_json_response(self, text: str) -> dict[str, Any]:
        """Parse JSON from AI response with repair."""
        import re

        try:
            return json.loads(text)
        except json.JSONDecodeError:
            pass

        cleaned = re.sub(r"^```(?:json)?\s*", "", text.strip())
        cleaned = re.sub(r"\s*```$", "", cleaned)
        try:
            return json.loads(cleaned)
        except json.JSONDecodeError:
            pass

        start = text.find("{")
        if start == -1:
            raise ExtractionError(f"No JSON in response: {text[:300]}")

        depth = 0
        end = start
        for i in range(start, len(text)):
            if text[i] == "{":
                depth += 1
            elif text[i] == "}":
                depth -= 1
                if depth == 0:
                    end = i + 1
                    break

        try:
            return json.loads(text[start:end])
        except json.JSONDecodeError:
            pass

        for i in range(end - 1, start, -1):
            if text[i] == "}":
                try:
                    return json.loads(text[start:i + 1])
                except json.JSONDecodeError:
                    continue

        raise ExtractionError(f"Could not parse JSON ({len(text)} chars)")
