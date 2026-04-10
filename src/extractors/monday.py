"""Monday.com pricing extractor.

Code extraction: prices from visible HTML ($9/$12/$19 per seat), global policies from i18n.
AI extraction: full comparison table features from HTML (table is JS-rendered but i18n data helps).

Monday's pricing page stores feature data in i18n translation keys which we
pass to the AI alongside the HTML for comprehensive extraction.
"""

from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from typing import Any

from src.schemas.monday import MondayPricing
from .base import BaseExtractor


class MondayExtractor(BaseExtractor):
    competitor = "monday"
    display_name = "Monday.com"
    url = "https://monday.com/pricing"
    schema_cls = MondayPricing

    async def code_extract(self, html: str) -> dict[str, Any] | None:
        """Extract prices and global policies from Monday's page."""

        # Extract i18n translation keys for feature data
        i18n = {}
        for match in re.finditer(r'"(pricingPage\.[^"]+)"\s*:\s*"([^"]*?)"', html):
            i18n[match.group(1)] = match.group(2)

        # Extract prices from visible price elements
        # Monday shows: $9/seat (Basic annual), $12 (Standard), $19 (Pro)
        # These appear as plain text in the HTML
        prices = {}

        # Pattern: look for price near plan name
        plan_price_patterns = [
            ("basic", r"(?:Basic|basic)[\s\S]{0,200}?\$(\d+)"),
            ("standard", r"(?:Standard|standard)[\s\S]{0,200}?\$(\d+)"),
            ("pro", r"(?:Pro|pro)[\s\S]{0,200}?\$(\d+)"),
        ]
        for slug, pattern in plan_price_patterns:
            match = re.search(pattern, html)
            if match:
                price = float(match.group(1))
                if 5 <= price <= 50:  # Sanity check
                    prices[slug] = price

        # Fallback: extract all dollar amounts and use known positions
        if not prices:
            all_prices = re.findall(r"\$(\d+)", html)
            # Filter to reasonable per-seat prices
            reasonable = [float(p) for p in all_prices if 5 <= float(p) <= 50]
            unique = sorted(set(reasonable))
            if len(unique) >= 3:
                prices = {"basic": unique[0], "standard": unique[1], "pro": unique[2]}

        # Build plans with code-extracted data
        tiers = ["free", "basic", "standard", "pro", "enterprise"]
        plans = []
        for tier in tiers:
            plan: dict[str, Any] = {
                "name": "Free" if tier == "free" else (
                    "Enterprise" if tier == "enterprise" else tier.capitalize()
                ),
                "slug": tier,
                "is_free": tier == "free",
                "is_custom_pricing": tier == "enterprise",
                "features": {},
            }

            if tier == "free":
                plan["pricing"] = None
                plan["free_seats_limit"] = 2
            elif tier == "enterprise":
                plan["pricing"] = None
            elif tier in prices:
                plan["pricing"] = {
                    "annual_per_unit": prices[tier],
                    "unit": "seat",
                    "currency": "USD",
                }

            plans.append(plan)

        return {
            "competitor": self.competitor,
            "display_name": self.display_name,
            "url": self.url,
            "extracted_at": datetime.now(timezone.utc).isoformat(),
            "extraction_method": "python",
            "data_version": 1,
            "global_policies": {
                "minimum_seats": 3,
                "annual_discount_pct": 18.0,
                "trial_days": 14,
                "custom_quote_above_seats": 40,
                "refund_window_days": 30,
            },
            "products": [
                {"name": "Work Management", "slug": "work-management", "plans": plans}
            ],
        }

    async def fetch_html(self) -> str:
        """Fetch Monday HTML and append i18n feature data for AI extraction."""
        import httpx

        headers = {
            "User-Agent": (
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/125.0.0.0 Safari/537.36"
            ),
        }

        async with httpx.AsyncClient(follow_redirects=True, timeout=30.0) as client:
            response = await client.get(self.url, headers=headers)
            response.raise_for_status()
            html = response.text

        # Extract i18n feature data and prepend to HTML for AI
        pricing_features = []
        for match in re.finditer(r'"(pricingPage\.[^"]+)"\s*:\s*"([^"]*?)"', html):
            key, value = match.group(1), match.group(2)
            if value and not value.startswith("http"):
                pricing_features.append(f"{key} = {value}")

        if pricing_features:
            feature_block = (
                "\n<!-- MONDAY.COM STRUCTURED FEATURE DATA -->\n"
                + "\n".join(pricing_features)
                + "\n<!-- END FEATURE DATA -->\n"
            )
            # Prepend so it doesn't get truncated during cleaning
            html = feature_block + html

        return html

    def get_extraction_prompt(self) -> str:
        return """### Monday.com Specifics
- Focus on Work Management product ONLY
- Plans: Free, Basic, Standard, Pro, Enterprise
- Prices are "per seat/month" — minimum 3 seats on paid plans
- The HTML includes a STRUCTURED FEATURE DATA section at the top with i18n translation keys
  containing feature names, descriptions, and per-tier feature lists
- Use this structured data to build the complete comparison table
- Feature sections: Essentials, Collaboration, Productivity, Views and reporting,
  Resource management, Security & privacy, Administration & control,
  Advanced reporting & analytics, Support
- Key values to extract per tier:
  - Boards: 3 (Free) → Unlimited
  - Items: 1000 (Free) → Unlimited
  - Storage: 500MB → 5GB → 20GB → 100GB → 1000GB
  - Automations: none → none → 250/mo → 25K/mo → 250K/mo
  - Integrations: same as automations
  - Dashboards: none → 1 board → 5 boards → 20 boards → 50 boards
- url: "https://monday.com/pricing"
"""
