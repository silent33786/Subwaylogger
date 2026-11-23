"""
Unit tests for Advanced Auto Ads data models, self-learning memory, recovery engine, and pipeline.
"""

import pytest
from pathlib import Path

from firefox_manager.automation.auto_ads_models import AutoAdsConfig
from firefox_manager.automation.auto_ads_engine import auto_ads_engine
from firefox_manager.automation.ad_pipeline_steps import EU_COUNTRIES
from firefox_manager.automation.ad_agent_memory import AdAgentMemory
from firefox_manager.automation.ad_agent_recovery import (
    AdAgentRecovery,
    NeedsHumanChallenge,
    PolicyRestrictionError,
)
from firefox_manager.automation.ad_pipeline_steps import DEFAULT_AD_PIPELINE, StepContext
from firefox_manager.automation.smart_locator import SmartLocator


def test_auto_ads_config_validation():
    """Verify validation and defaults in AutoAdsConfig."""
    cfg = AutoAdsConfig(
        profile_id="test-profile-123",
        target_url="https://example.com/shop",
        ad_headline="Big Sale 50% Off",
        ad_description="Shop our latest collection with huge discounts today.",
        cta_button="Shop Now",
        target_countries=["United Kingdom", "France"],
        daily_budget=15.0,
        duration_days=5,
    )
    assert cfg.profile_id == "test-profile-123"
    assert cfg.daily_budget == 15.0
    assert cfg.cta_button == "Shop Now"
    assert cfg.placement_facebook is True
    assert cfg.placement_instagram is True
    assert cfg.enable_pro_mode is True
    assert cfg.unlock_profile_if_locked is True
    assert cfg.max_retries_per_step == 3
    assert cfg.diagnostic_screenshots is True


def test_eu_compliance_rules():
    """Verify EU country detection, and that no fake payee is invented.

    The old code picked a random fake company name as the EU payee.
    That list has been removed: targeting the EU without a real
    payee_name must raise, and the engine must not invent one.
    """
    assert "germany" in EU_COUNTRIES
    assert "france" in EU_COUNTRIES
    assert "united kingdom" in EU_COUNTRIES
    # No fake-payee names exist anywhere in the pipeline any more.
    import firefox_manager.automation.ad_pipeline_steps as steps
    import firefox_manager.automation.auto_ads_engine as engine

    assert not hasattr(steps, "RANDOM_PAYEE_NAMES")
    assert not hasattr(engine, "RANDOM_PAYEE_NAMES")


def test_engine_initialization():
    """Verify engine instance and helper existence."""
    assert auto_ads_engine is not None
    assert hasattr(auto_ads_engine, "run_auto_ads_workflow")
    assert hasattr(auto_ads_engine, "check_for_human_challenge")
    assert hasattr(auto_ads_engine, "pause")
    assert hasattr(auto_ads_engine, "resume")
    assert hasattr(auto_ads_engine, "stop")

    # Test state transitions
    auto_ads_engine.pause()
    assert auto_ads_engine.is_paused is True
    auto_ads_engine.resume()
    assert auto_ads_engine.is_paused is False
    auto_ads_engine.stop()
    assert auto_ads_engine.should_stop is True
    auto_ads_engine.should_stop = False


def test_ad_agent_memory(tmp_path):
    """Verify Laplace Bayesian scoring and ranking in self-learning memory."""
    mem_file = tmp_path / "test_memory.json"
    mem = AdAgentMemory(memory_file=mem_file)

    # Initially uniform score: (0 + 1) / (0 + 0 + 2) = 0.5
    assert mem.score("step1|optA") == 0.5

    # Record 3 successes and 1 failure for optA -> (3 + 1) / (3 + 1 + 2) = 4/6 = 0.667
    mem.record("step1|optA", True)
    mem.record("step1|optA", True)
    mem.record("step1|optA", True)
    mem.record("step1|optA", False)
    assert pytest.approx(mem.score("step1|optA"), 0.001) == (4 / 6)

    # Record 0 successes and 3 failures for optB -> (0 + 1) / (0 + 3 + 2) = 1/5 = 0.2
    mem.record("step1|optB", False)
    mem.record("step1|optB", False)
    mem.record("step1|optB", False)
    assert pytest.approx(mem.score("step1|optB"), 0.001) == 0.2

    # Ranking should place optA first
    ranked = mem.rank("step1", ["optB", "optA", "optC"])
    assert ranked[0] == "optA"
    assert ranked[1] == "optC"  # 0.5 prior
    assert ranked[2] == "optB"  # 0.2

    # Verify persistence to disk
    mem2 = AdAgentMemory(memory_file=mem_file)
    assert pytest.approx(mem2.score("step1|optA"), 0.001) == (4 / 6)

    # Stats summary
    stats = mem.get_stats()
    assert stats["total_successes"] == 3
    assert stats["total_failures"] == 4

    # Reset
    mem.clear()
    assert mem.score("step1|optA") == 0.5


def test_ad_agent_recovery_classification():
    """Verify error classification categories."""
    rec = AdAgentRecovery()

    # Security detection
    err_sec = RuntimeError("Facebook checkpoint required: confirm your identity")
    assert rec.classify_failure(0, err_sec) == "security"

    # 2FA
    err_2fa = RuntimeError("Two-factor authentication code required")
    assert rec.classify_failure(0, err_2fa) == "security"

    # Payment
    err_pay = RuntimeError("Please add payment method to continue")
    assert rec.classify_failure(0, err_pay) == "payment_required"

    # Logged out
    err_login = RuntimeError("Redirected to login.php on facebook")
    assert rec.classify_failure(0, err_login) == "logged_out"

    # Policy restriction
    err_restr = RuntimeError("Facebook: account restricted from advertising")
    assert rec.classify_failure(0, err_restr) == "ad_restricted"

    # Timeout / Element missing
    err_to = TimeoutError("Element timeout: button not found")
    assert rec.classify_failure(0, err_to) == "element_missing"


def test_pipeline_steps_structure():
    """Verify all 8 modular pipeline steps are loaded and ordered correctly."""
    assert len(DEFAULT_AD_PIPELINE) == 8
    expected_names = [
        "profile_resolution",
        "unlock_profile",
        "professional_mode",
        "navigate_ad_center",
        "set_goal",
        "fill_creative",
        "audience_budget",
        "publish",
    ]
    actual_names = [step.name for step in DEFAULT_AD_PIPELINE]
    assert actual_names == expected_names
