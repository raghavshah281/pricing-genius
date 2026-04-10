"""Notion-specific pricing schema.

Notion has 4 tiers: Free, Plus, Business, Enterprise.
Key differences from others:
- Page history measured in days
- External guest limits (10 for free, unlimited for paid)
- Teamspace types (open, closed, private) differ by tier
- AI add-on sold separately with credit packs
- Web publishing features (notion.site domains, custom domains)
- AI data retention differs by tier (30 days vs zero retention)
"""

from __future__ import annotations

from pydantic import BaseModel, Field, field_validator, model_validator

from .common import CompetitorBase, Feature, PricingInfo, TrialInfo


class NotionPlan(BaseModel):
    """A single Notion pricing tier."""

    name: str = Field(description="Display name: Free, Plus, Business, Enterprise")
    slug: str = Field(description="Lowercase: free, plus, business, enterprise")
    label: str | None = Field(None, description="Marketing label: 'Recommended'")
    is_free: bool = Field(default=False)
    is_custom_pricing: bool = Field(default=False)
    pricing: PricingInfo | None = None

    # Notion-specific limits
    file_upload_limit: str = Field(description="Max file upload: '5 MB' or 'unlimited'")
    page_history_days: int | str = Field(description="Page history: 7, 30, 90, or 'unlimited'")
    external_guests: int | str = Field(description="Guest limit: 10 or 'unlimited'")
    charts: int | str = Field(description="Chart limit: 1 or 'unlimited'")
    notion_site_domains: int = Field(description="Number of notion.site domains allowed")
    ai_data_retention_days: int = Field(
        description="AI data retention: 30 (standard) or 0 (zero retention for Enterprise)"
    )

    # Teamspace capabilities
    teamspaces_open_closed: bool = Field(default=False, description="Open/closed teamspaces available")
    teamspaces_private: bool = Field(default=False, description="Private teamspaces available")

    # Features by category
    features: dict[str, list[Feature]] = Field(
        default_factory=dict,
        description="Categories: content_collab, ai, integrations, databases_automation, web_publishing, security_admin, support"
    )

    @field_validator("features", mode="before")
    @classmethod
    def coerce_features(cls, v):
        return v if v is not None else {}

    @model_validator(mode="after")
    def pricing_consistency(self) -> "NotionPlan":
        if self.is_free and self.pricing is not None and self.pricing.monthly_per_unit and self.pricing.monthly_per_unit > 0:
            raise ValueError("Free plan should not have a price > 0")
        # Note: Notion Enterprise has published prices, so we allow
        # is_custom_pricing=True with pricing info for Notion
        return self


class NotionAddOn(BaseModel):
    """Notion add-on (AI, Custom Domains, etc.)."""

    name: str
    monthly_price: str | None = Field(None, description="e.g., '$10/member/month'")
    annual_price: str | None = Field(None, description="e.g., '$8/member/month'")
    description: str | None = None


class NotionSpecialProgram(BaseModel):
    """Special discount programs."""

    name: str = Field(description="e.g., 'Student/Educator Discount'")
    description: str


class NotionPricing(CompetitorBase):
    """Complete Notion pricing data."""

    plans: list[NotionPlan]
    add_ons: list[NotionAddOn] = Field(default_factory=list)
    special_programs: list[NotionSpecialProgram] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_plan_count(self) -> "NotionPricing":
        if len(self.plans) < 3:
            raise ValueError("Notion should have at least 3 plans")
        return self
