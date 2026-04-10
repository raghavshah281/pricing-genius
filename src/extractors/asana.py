"""Asana pricing extractor.

Code extraction: prices from data-cy attributes + JSON-LD (authoritative).
AI extraction: features from HTML comparison table.

Asana has reliable price data in data-cy="starter-price" etc. attributes
and JSON-LD structured data. Monthly prices appear in visible text.
"""

from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from typing import Any

from bs4 import BeautifulSoup

from src.schemas.asana import AsanaPricing
from .base import BaseExtractor


class AsanaExtractor(BaseExtractor):
    competitor = "asana"
    display_name = "Asana"
    url = "https://asana.com/pricing"
    schema_cls = AsanaPricing

    async def code_extract(self, html: str) -> dict[str, Any] | None:
        """Extract prices from Asana's HTML structured data."""
        soup = BeautifulSoup(html, "html.parser")

        # Extract annual prices from data-cy attributes
        annual_prices = {}
        for el in soup.find_all(attrs={"data-cy": re.compile(r"(\w+)-price")}):
            match = re.match(r"(\w+)-price", el.get("data-cy", ""))
            if match:
                plan_slug = match.group(1)
                price_text = el.get_text(strip=True)
                price_match = re.search(r"\$?([\d.]+)", price_text)
                if price_match:
                    annual_prices[plan_slug] = float(price_match.group(1))

        # Extract monthly prices from "billed monthly" text
        monthly_prices = {}
        for match in re.finditer(r"\$([\d.]+)\s+billed monthly", html):
            price = float(match.group(1))
            # Map to plan by finding nearest preceding plan name
            before = html[max(0, match.start() - 500):match.start()]
            for plan in ["starter", "advanced"]:
                if plan in before.lower():
                    monthly_prices[plan] = price

        # Also try JSON-LD
        json_ld_blocks = re.findall(
            r'<script[^>]*type="application/ld\+json"[^>]*>([\s\S]*?)</script>', html
        )
        for block in json_ld_blocks:
            try:
                data = json.loads(block)
                if isinstance(data, dict) and "offers" in data:
                    for offer in data["offers"]:
                        name = offer.get("name", "").lower()
                        price = offer.get("price")
                        if name and price:
                            if name not in annual_prices:
                                annual_prices[name] = float(price)
            except (json.JSONDecodeError, ValueError):
                continue

        # Build plans
        PLAN_DEFS = [
            {"name": "Personal", "slug": "personal", "is_free": True, "tagline": "For individuals"},
            {"name": "Starter", "slug": "starter", "tagline": "For growing teams"},
            {"name": "Advanced", "slug": "advanced", "tagline": "For companies managing portfolios"},
            {"name": "Enterprise", "slug": "enterprise", "is_custom": True, "tagline": "For organizations needing advanced controls"},
            {"name": "Enterprise+", "slug": "enterprise-plus", "is_custom": True, "tagline": "For strict compliance requirements"},
        ]

        plans = []
        for plan_def in PLAN_DEFS:
            slug = plan_def["slug"]
            is_free = plan_def.get("is_free", False)
            is_custom = plan_def.get("is_custom", False)

            plan: dict[str, Any] = {
                "name": plan_def["name"],
                "slug": slug,
                "tagline": plan_def.get("tagline"),
                "is_free": is_free,
                "is_custom_pricing": is_custom,
                "features": {},
            }

            if is_free:
                plan["pricing"] = None
                plan["users"] = {"min": 1, "max": 2}
            elif is_custom:
                plan["pricing"] = None
            else:
                annual = annual_prices.get(slug)
                monthly = monthly_prices.get(slug)
                if annual or monthly:
                    plan["pricing"] = {
                        "annual_per_unit": annual,
                        "monthly_per_unit": monthly,
                        "unit": "user",
                        "currency": "USD",
                    }

            plans.append(plan)

        if not plans:
            return None

        return {
            "competitor": self.competitor,
            "display_name": self.display_name,
            "url": self.url,
            "extracted_at": datetime.now(timezone.utc).isoformat(),
            "extraction_method": "python",
            "data_version": 1,
            "plans": plans,
        }

    def get_extraction_prompt(self) -> str:
        return """### Asana Specifics
- Plans: Personal (free), Starter, Advanced, Enterprise, Enterprise+
- Prices are "per user/month"
- Extract the FULL comparison table — it has 100+ feature rows across categories
- Feature categories: Views, Task Management, Automation, Reporting, Collaboration, Time Tracking, Integrations, Admin & Security, Compliance, AI, Support
- For each feature, capture: name, available (true/false per plan), value (specific limit if shown)
- url: "https://asana.com/pricing"
"""
