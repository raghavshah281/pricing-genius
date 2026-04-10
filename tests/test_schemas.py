"""Tests for Pydantic schemas — validates data integrity and constraints."""

import json
import pytest
from datetime import datetime, timezone
from pathlib import Path

from src.schemas.common import BillingUnit, ExtractionMethod, Feature, PricingInfo, UserLimits
from src.schemas.smartsheet import SmartsheetPlan, SmartsheetPricing
from src.schemas.wrike import WrikePlan, WrikePricing
from src.schemas.asana import AsanaPlan, AsanaPricing
from src.schemas.notion import NotionPlan, NotionPricing
from src.schemas.monday import MondayPlan, MondayPricing, MondayProduct

DATA_DIR = Path(__file__).parent.parent / "data"


class TestPricingInfo:
    def test_valid_pricing(self):
        p = PricingInfo(monthly_per_unit=10.0, annual_per_unit=8.0, unit=BillingUnit.SEAT)
        assert p.monthly_per_unit == 10.0
        assert p.annual_per_unit == 8.0
        assert p.unit == BillingUnit.SEAT

    def test_negative_price_rejected(self):
        with pytest.raises(ValueError, match="non-negative"):
            PricingInfo(monthly_per_unit=-5.0, annual_per_unit=8.0, unit=BillingUnit.SEAT)

    def test_discount_out_of_range_rejected(self):
        with pytest.raises(ValueError, match="between 0 and 100"):
            PricingInfo(monthly_per_unit=10.0, unit=BillingUnit.SEAT, annual_discount_pct=150.0)

    def test_null_prices_allowed(self):
        p = PricingInfo(unit=BillingUnit.USER)
        assert p.monthly_per_unit is None
        assert p.annual_per_unit is None


class TestSmartsheetSchema:
    def test_custom_plan_no_pricing(self):
        plan = SmartsheetPlan(
            name="Enterprise", slug="enterprise",
            is_custom_pricing=True, pricing=None,
            automations_per_month="unlimited",
        )
        assert plan.is_custom_pricing

    def test_custom_plan_with_pricing_rejected(self):
        with pytest.raises(ValueError, match="Custom pricing plans should not have pricing"):
            SmartsheetPlan(
                name="Enterprise", slug="enterprise",
                is_custom_pricing=True,
                pricing=PricingInfo(monthly_per_unit=100, unit=BillingUnit.MEMBER),
                automations_per_month="unlimited",
            )

    def test_non_custom_plan_requires_pricing(self):
        with pytest.raises(ValueError, match="Non-custom plans must have pricing"):
            SmartsheetPlan(
                name="Pro", slug="pro",
                is_custom_pricing=False, pricing=None,
                automations_per_month=250,
            )

    def test_minimum_plan_count(self):
        with pytest.raises(ValueError, match="at least 2 plans"):
            SmartsheetPricing(
                competitor="smartsheet", display_name="Smartsheet",
                url="https://example.com", extracted_at=datetime.now(timezone.utc),
                extraction_method=ExtractionMethod.MANUAL,
                plans=[SmartsheetPlan(
                    name="Pro", slug="pro", is_custom_pricing=False,
                    pricing=PricingInfo(monthly_per_unit=10, unit=BillingUnit.MEMBER),
                    automations_per_month=250,
                )],
            )

    def test_load_seeded_data(self):
        path = DATA_DIR / "smartsheet.json"
        if not path.exists():
            pytest.skip("Seed data not generated yet")
        raw = json.loads(path.read_text())
        pricing = SmartsheetPricing.model_validate(raw)
        assert pricing.competitor == "smartsheet"
        assert len(pricing.plans) >= 4
        plan_names = [p.name for p in pricing.plans]
        assert "Pro" in plan_names
        assert "Business" in plan_names


class TestWrikeSchema:
    def test_free_plan_no_price(self):
        plan = WrikePlan(name="Free", slug="free", is_free=True)
        assert plan.is_free

    def test_free_plan_with_price_rejected(self):
        with pytest.raises(ValueError, match="Free plan should not have a price"):
            WrikePlan(
                name="Free", slug="free", is_free=True,
                pricing=PricingInfo(monthly_per_unit=10, unit=BillingUnit.USER),
            )

    def test_load_seeded_data(self):
        path = DATA_DIR / "wrike.json"
        if not path.exists():
            pytest.skip("Seed data not generated yet")
        raw = json.loads(path.read_text())
        pricing = WrikePricing.model_validate(raw)
        assert pricing.competitor == "wrike"
        assert len(pricing.plans) >= 5
        slugs = [p.slug for p in pricing.plans]
        assert "free" in slugs
        assert "team" in slugs


class TestAsanaSchema:
    def test_load_seeded_data(self):
        path = DATA_DIR / "asana.json"
        if not path.exists():
            pytest.skip("Seed data not generated yet")
        raw = json.loads(path.read_text())
        pricing = AsanaPricing.model_validate(raw)
        assert pricing.competitor == "asana"
        assert len(pricing.plans) >= 3  # At minimum: Personal, Starter, Advanced
        plan_names = [p.name for p in pricing.plans]
        assert "Starter" in plan_names or "Personal" in plan_names

    def test_enterprise_is_custom(self):
        path = DATA_DIR / "asana.json"
        if not path.exists():
            pytest.skip("Seed data not generated yet")
        raw = json.loads(path.read_text())
        pricing = AsanaPricing.model_validate(raw)
        enterprise = [p for p in pricing.plans if "enterprise" in p.slug.lower()]
        if enterprise:
            assert enterprise[0].is_custom_pricing


class TestNotionSchema:
    def test_load_seeded_data(self):
        path = DATA_DIR / "notion.json"
        if not path.exists():
            pytest.skip("Seed data not generated yet")
        raw = json.loads(path.read_text())
        pricing = NotionPricing.model_validate(raw)
        assert pricing.competitor == "notion"
        assert len(pricing.plans) >= 3
        plan_names = [p.name for p in pricing.plans]
        assert "Free" in plan_names or any(p.is_free for p in pricing.plans)


class TestMondaySchema:
    def test_load_seeded_data(self):
        path = DATA_DIR / "monday.json"
        if not path.exists():
            pytest.skip("Seed data not generated yet")
        raw = json.loads(path.read_text())
        pricing = MondayPricing.model_validate(raw)
        assert pricing.competitor == "monday"
        assert len(pricing.products) >= 1
        assert pricing.global_policies.minimum_seats == 3

        wm = [p for p in pricing.products if p.slug == "work-management"][0]
        assert len(wm.plans) >= 3

    def test_minimum_product_count(self):
        with pytest.raises(ValueError, match="at least 1 product"):
            MondayPricing(
                competitor="monday", display_name="Monday.com",
                url="https://example.com", extracted_at=datetime.now(timezone.utc),
                extraction_method=ExtractionMethod.MANUAL,
                products=[],
            )


class TestCrossCompetitorComparability:
    """Verify that all seeded data can be loaded and compared."""

    @pytest.fixture
    def all_data(self):
        from src.storage.json_store import COMPETITOR_SLUGS, load_competitor_raw
        data = {}
        for slug in COMPETITOR_SLUGS:
            path = DATA_DIR / f"{slug}.json"
            if path.exists():
                data[slug] = load_competitor_raw(slug)
        return data

    def test_all_competitors_have_data(self, all_data):
        assert len(all_data) == 5, f"Expected 5 competitors, got {len(all_data)}"

    def test_all_have_extraction_metadata(self, all_data):
        for slug, data in all_data.items():
            assert "extracted_at" in data, f"{slug} missing extracted_at"
            assert "extraction_method" in data, f"{slug} missing extraction_method"
            assert "competitor" in data, f"{slug} missing competitor"

    def test_all_pricing_in_usd(self, all_data):
        """All prices must be in USD for comparability."""
        for slug, data in all_data.items():
            plans = self._get_plans(slug, data)
            for plan in plans:
                pricing = plan.get("pricing")
                if pricing:
                    assert pricing.get("currency", "USD") == "USD", \
                        f"{slug}/{plan.get('name')}: currency is {pricing.get('currency')}, expected USD"

    def test_annual_not_greater_than_monthly(self, all_data):
        """Annual per-unit price should be <= monthly (it's a discount)."""
        for slug, data in all_data.items():
            plans = self._get_plans(slug, data)
            for plan in plans:
                pricing = plan.get("pricing")
                if pricing and pricing.get("monthly_per_unit") and pricing.get("annual_per_unit"):
                    monthly = pricing["monthly_per_unit"]
                    annual = pricing["annual_per_unit"]
                    assert annual <= monthly, (
                        f"{slug}/{plan.get('name')}: annual ({annual}) > monthly ({monthly}). "
                        "Annual per-unit should be less than or equal to monthly."
                    )

    def test_prices_are_per_month_not_per_year(self, all_data):
        """Sanity check: prices should be per-month (< $500/unit)."""
        for slug, data in all_data.items():
            plans = self._get_plans(slug, data)
            for plan in plans:
                pricing = plan.get("pricing")
                if pricing:
                    for field in ["monthly_per_unit", "annual_per_unit"]:
                        val = pricing.get(field)
                        if val is not None:
                            # Smartsheet Business is $2419/month which is an outlier but valid
                            if slug == "smartsheet" and plan.get("slug") == "business":
                                continue
                            assert val < 500, (
                                f"{slug}/{plan.get('name')}: {field}={val} seems too high. "
                                "Prices should be per-unit per-month, not annual totals."
                            )

    def test_free_plans_have_no_price(self, all_data):
        for slug, data in all_data.items():
            plans = self._get_plans(slug, data)
            for plan in plans:
                if plan.get("is_free"):
                    pricing = plan.get("pricing")
                    if pricing:
                        assert pricing.get("monthly_per_unit") in (None, 0), \
                            f"{slug}/{plan.get('name')}: free plan has price {pricing.get('monthly_per_unit')}"

    def test_custom_plans_have_no_price(self, all_data):
        for slug, data in all_data.items():
            # Skip Notion — Enterprise has published prices despite being "custom"
            if slug == "notion":
                continue
            plans = self._get_plans(slug, data)
            for plan in plans:
                if plan.get("is_custom_pricing"):
                    assert plan.get("pricing") is None, \
                        f"{slug}/{plan.get('name')}: custom plan should have pricing=null"

    def _get_plans(self, slug: str, data: dict) -> list[dict]:
        if slug == "monday":
            plans = []
            for product in data.get("products", []):
                plans.extend(product.get("plans", []))
            return plans
        return data.get("plans", [])
