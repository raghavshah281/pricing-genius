"""Asana-specific pricing schema.

Asana has 5 tiers: Personal, Starter, Advanced, Enterprise, Enterprise+.
Key differences from others:
- AI Studio as a separate add-on with credit-based pricing
- Seat scaling increments (different increments at different team sizes)
- Org-wide automation limits (not per-seat)
- Estimated prices for Enterprise tiers (not published)
- Compliance-focused Enterprise+ tier (HIPAA, EKM, data residency)
"""

from __future__ import annotations

from pydantic import BaseModel, Field, field_validator, model_validator

from .common import CompetitorBase, Feature, PricingInfo, TrialInfo, UserLimits


class AsanaPlan(BaseModel):
    """A single Asana pricing tier."""

    name: str = Field(description="Display name: Personal, Starter, Advanced, Enterprise, Enterprise+")
    slug: str = Field(description="Lowercase: personal, starter, advanced, enterprise, enterprise-plus")
    tagline: str | None = Field(None, description="Marketing tagline for this tier")
    is_free: bool = Field(default=False)
    is_custom_pricing: bool = Field(default=False)
    pricing: PricingInfo | None = None
    estimated_price_per_user_month: float | None = Field(
        None, description="Estimated price for Enterprise tiers (not officially published)"
    )
    trial: TrialInfo | None = None

    # User limits
    users: UserLimits | None = None

    # Resource limits
    automations_per_month_org: int | str | None = Field(
        None, description="Org-wide automations per month: int or 'unlimited'"
    )
    ai_actions_per_month: int | str | None = Field(
        None, description="Asana Intelligence actions per month: int or 'unlimited'"
    )
    storage_per_file_mb: int | None = Field(
        None, description="Max file upload size in MB (e.g., 100)"
    )
    portfolios: int | str | None = Field(
        None, description="Portfolio limit: int or 'unlimited'"
    )
    projects_per_portfolio: int | str | None = Field(
        None, description="Projects per portfolio: int or 'unlimited'"
    )

    # Features by category
    features: dict[str, list[Feature]] = Field(
        default_factory=dict,
        description="Categories: views, task_mgmt, automation, reporting, collaboration, time_tracking, integrations, admin_security, compliance, ai, support"
    )

    @field_validator("features", mode="before")
    @classmethod
    def coerce_features(cls, v):
        return v if v is not None else {}

    @model_validator(mode="after")
    def pricing_consistency(self) -> "AsanaPlan":
        if self.is_free and self.pricing is not None and self.pricing.monthly_per_unit and self.pricing.monthly_per_unit > 0:
            raise ValueError("Free plan should not have a price > 0")
        if self.is_custom_pricing and self.pricing is not None:
            raise ValueError("Custom pricing plans should not have pricing info")
        return self


class AsanaAIStudioTier(BaseModel):
    """AI Studio add-on tier."""

    name: str = Field(description="e.g., 'Basic', 'Plus', 'Pro'")
    description: str | None = None
    pricing: str | None = Field(None, description="Pricing description or 'included'")
    billing: str | None = Field(None, description="e.g., 'monthly/annual', 'annual only'")


class AsanaAIStudio(BaseModel):
    """AI Studio add-on details."""

    eligible_plans: list[str] = Field(default_factory=list, description="Plan slugs that support AI Studio")
    tiers: list[AsanaAIStudioTier] = Field(default_factory=list)
    credit_packs: list[dict] | None = Field(
        default_factory=list,
        description="Credit pack options: [{credits: 1000, price: '$100'}]"
    )


class SeatScalingRule(BaseModel):
    """Seat scaling increment rule."""

    range_start: int
    range_end: int | None = Field(None, description="None means unlimited")
    increment: int = Field(description="Seat increment for this range")


class AsanaPricing(CompetitorBase):
    """Complete Asana pricing data."""

    plans: list[AsanaPlan]
    ai_studio: AsanaAIStudio | None = None
    seat_scaling: list[SeatScalingRule] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_plan_count(self) -> "AsanaPricing":
        if len(self.plans) < 3:
            raise ValueError("Asana should have at least 3 plans")
        return self
