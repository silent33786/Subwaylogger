"""
Auto Ads Data Models and Configuration Schemas.
Stores all user-defined parameters for Facebook Profile Unlock, Pro Mode, and Ad Creation.
"""

from typing import List, Optional
from pydantic import BaseModel, Field


class AutoAdsConfig(BaseModel):
    """Container for all user input collected up-front in the dashboard."""

    profile_id: str
    target_url: str = Field(..., description="Destination website URL for website visitors/traffic")
    ad_headline: str = Field(..., description="Ad Headline text")
    ad_description: str = Field(..., description="Ad primary text/description")
    cta_button: str = Field(default="Learn More", description="Call-to-Action button label")
    image_path: Optional[str] = Field(default=None, description="Path to creative image on disk")

    # Audience & Geography
    target_countries: List[str] = Field(default_factory=lambda: ["United States"])
    payee_name: Optional[str] = Field(default=None, description="Payee / Beneficiary name for European compliance")

    # Budget & Placements
    daily_budget: float = Field(default=5.0, ge=1.0)
    duration_days: int = Field(default=7, ge=1, le=90)
    placement_facebook: bool = True
    placement_instagram: bool = True

    # Adaptive & Self-Learning Options
    enable_pro_mode: bool = True
    skip_pro_mode_if_active: bool = True
    unlock_profile_if_locked: bool = True
    max_retries_per_step: int = Field(default=3, ge=1, le=10)
    diagnostic_screenshots: bool = True
