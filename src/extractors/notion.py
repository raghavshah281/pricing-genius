"""Notion pricing extractor.

Code extraction: prices from __NEXT_DATA__.props.pageProps.plans (authoritative).
AI extraction: features from HTML (comparison table is client-rendered).

Notion's __NEXT_DATA__ contains exact pricing in cents for all plans including Enterprise.
"""

from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from typing import Any

from src.schemas.notion import NotionPricing
from .base import BaseExtractor


class NotionExtractor(BaseExtractor):
    competitor = "notion"
    display_name = "Notion"
    url = "https://www.notion.com/pricing"
    schema_cls = NotionPricing

    async def code_extract(self, html: str) -> dict[str, Any] | None:
        """Extract prices from Notion's __NEXT_DATA__ — authoritative source."""

        # Extract __NEXT_DATA__
        nd_match = re.search(
            r'<script[^>]*id="__NEXT_DATA__"[^>]*>([\s\S]*?)</script>', html
        )
        if not nd_match:
            return None

        try:
            nd = json.loads(nd_match.group(1))
        except json.JSONDecodeError:
            return None

        plans_data = nd.get("props", {}).get("pageProps", {}).get("plans", {})
        if not plans_data:
            return None

        # Map Notion's plan names to our schema
        PLAN_MAP = {
            "student": {"name": "Free", "slug": "free", "is_free": True, "is_custom_pricing": False},
            "plus": {"name": "Plus", "slug": "plus", "is_free": False, "is_custom_pricing": False},
            "business": {"name": "Business", "slug": "business", "is_free": False, "is_custom_pricing": False, "label": "Recommended"},
            "enterprise": {"name": "Enterprise", "slug": "enterprise", "is_free": False, "is_custom_pricing": True},
        }

        # Notion-specific defaults per plan
        PLAN_LIMITS = {
            "free": {
                "file_upload_limit": "5 MB",
                "page_history_days": 7,
                "external_guests": 10,
                "charts": 1,
                "notion_site_domains": 1,
                "ai_data_retention_days": 30,
                "teamspaces_open_closed": False,
                "teamspaces_private": False,
            },
            "plus": {
                "file_upload_limit": "unlimited",
                "page_history_days": 30,
                "external_guests": "unlimited",
                "charts": "unlimited",
                "notion_site_domains": 5,
                "ai_data_retention_days": 30,
                "teamspaces_open_closed": True,
                "teamspaces_private": False,
            },
            "business": {
                "file_upload_limit": "unlimited",
                "page_history_days": 90,
                "external_guests": "unlimited",
                "charts": "unlimited",
                "notion_site_domains": 5,
                "ai_data_retention_days": 30,
                "teamspaces_open_closed": True,
                "teamspaces_private": True,
            },
            "enterprise": {
                "file_upload_limit": "unlimited",
                "page_history_days": "unlimited",
                "external_guests": "unlimited",
                "charts": "unlimited",
                "notion_site_domains": 5,
                "ai_data_retention_days": 0,
                "teamspaces_open_closed": True,
                "teamspaces_private": True,
            },
        }

        plans = []
        for product_key, plan_info in PLAN_MAP.items():
            product_data = plans_data.get(product_key, {}).get("USD", {})
            if not product_data:
                continue

            month_data = product_data.get("month", {})
            year_data = product_data.get("year", {})

            # unit_amount is in cents
            monthly_cents = month_data.get("unit_amount", 0)
            yearly_cents = year_data.get("unit_amount", 0)

            # Convert: monthly price = cents/100, annual per-month = yearly cents / 12 / 100
            monthly_price = monthly_cents / 100 if monthly_cents else None
            annual_price = round(yearly_cents / 12 / 100, 2) if yearly_cents else None

            plan: dict[str, Any] = {
                **plan_info,
                **PLAN_LIMITS.get(plan_info["slug"], {}),
                "features": {},
            }

            if plan_info["is_free"]:
                plan["pricing"] = None
                monthly_price = None
                annual_price = None
            elif plan_info["is_custom_pricing"]:
                # Notion Enterprise actually has published prices!
                if monthly_price and monthly_price > 0:
                    plan["is_custom_pricing"] = False
                    plan["pricing"] = {
                        "monthly_per_unit": monthly_price,
                        "annual_per_unit": annual_price,
                        "unit": "member",
                        "currency": "USD",
                    }
                else:
                    plan["pricing"] = None
            else:
                plan["pricing"] = {
                    "monthly_per_unit": monthly_price if monthly_price and monthly_price > 0 else None,
                    "annual_per_unit": annual_price if annual_price and annual_price > 0 else None,
                    "unit": "member",
                    "currency": "USD",
                }

            plans.append(plan)

        # Extract add-ons from the same data
        add_ons = []
        ai_data = plans_data.get("ai", {}).get("USD", {})
        if ai_data:
            ai_month = ai_data.get("month", {}).get("unit_amount", 0) / 100
            ai_year = ai_data.get("year", {}).get("unit_amount", 0) / 12 / 100
            add_ons.append({
                "name": "AI Add-on",
                "description": "For Free/Plus plans",
                "monthly_price": f"${ai_month:.0f}/member/month",
                "annual_price": f"${ai_year:.2f}/member/month",
            })

        sites_data = plans_data.get("sites_custom_hostnames", {}).get("USD", {})
        if sites_data:
            sites_month = sites_data.get("month", {}).get("unit_amount", 0) / 100
            add_ons.append({
                "name": "Custom Domains & Branding",
                "monthly_price": f"${sites_month:.0f}/month/domain",
            })

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
            "add_ons": add_ons,
        }

    def get_extraction_prompt(self) -> str:
        return """### Notion Specifics
- Plans: Free, Plus, Business, Enterprise
- Prices are "per member/month"
- Extract the FULL comparison table with ALL features per plan
- Feature categories: Content & Collaboration, AI, Integrations, Databases & Automation, Web Publishing, Security & Admin, Support
- For each feature row, capture: feature name, and value per plan (checkmark, dash, or specific value)
- Extract add-ons: AI Add-on, Custom Agents, Custom Domains
- url: "https://www.notion.com/pricing"
"""
