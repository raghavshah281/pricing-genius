"""Shared types used across all competitor pricing schemas."""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any, Union

from pydantic import BaseModel, Field, field_validator


class BillingUnit(str, Enum):
    SEAT = "seat"
    MEMBER = "member"
    USER = "user"
    FLAT = "flat"


class ExtractionMethod(str, Enum):
    PYTHON = "python"
    AI = "ai"
    HYBRID = "hybrid"
    MANUAL = "manual"


class PricingInfo(BaseModel):
    """Pricing for a single tier. All monetary values are in USD per month."""

    monthly_per_unit: float | None = Field(
        None, description="Price per unit per month when billed monthly"
    )
    annual_per_unit: float | None = Field(
        None, description="Price per unit per month when billed annually"
    )
    unit: BillingUnit = Field(description="What the price is per (seat, member, user, flat)")
    currency: str = Field(default="USD")
    annual_discount_pct: float | None = Field(
        None, description="Percentage discount for annual billing"
    )

    @field_validator("monthly_per_unit", "annual_per_unit")
    @classmethod
    def price_must_be_non_negative(cls, v: float | None) -> float | None:
        if v is not None and v < 0:
            raise ValueError("Price must be non-negative")
        return v

    @field_validator("annual_discount_pct")
    @classmethod
    def discount_must_be_percentage(cls, v: float | None) -> float | None:
        if v is not None and (v < 0 or v > 100):
            raise ValueError("Discount must be between 0 and 100")
        return v


class Feature(BaseModel):
    """A single feature within a category."""

    name: str
    available: bool = True
    value: Union[str, int, float, bool, None] = Field(
        None, description="Specific value if not just boolean (e.g., '250', 'unlimited')"
    )
    note: str | None = Field(None, description="Additional context (e.g., 'add-on', 'NEW')")


class UserLimits(BaseModel):
    """Min/max user constraints for a plan."""

    min: int | None = None
    max: int | None = Field(None, description="None means unlimited")


class TrialInfo(BaseModel):
    """Trial availability for a plan."""

    days: int
    credit_card_required: bool = False


class CompetitorBase(BaseModel):
    """Base model for all competitor pricing data."""

    competitor: str = Field(description="Competitor slug (e.g., 'smartsheet')")
    display_name: str = Field(description="Display name (e.g., 'Smartsheet')")
    url: str = Field(description="Pricing page URL")
    extracted_at: datetime = Field(description="When this data was extracted (ISO 8601)")
    extraction_method: ExtractionMethod
    data_version: int = Field(
        default=1, description="Schema version for tracking format changes"
    )

    def comparable_key(self) -> str:
        """Key for comparing extractions of the same competitor over time."""
        return self.competitor
