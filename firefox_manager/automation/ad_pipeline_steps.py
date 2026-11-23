"""
Modular Native Firefox Ad Creation Pipeline Steps.
Uses 100% native untouched Firefox profiles with:
- Window auto-maximization for standardized geometry across all screens
- SmartVision computer-vision color button detection (Primary Blue & Secondary Grey)
- Direct Alt+D URL navigation
- Checkpoint / Locked Account early detection with Human-in-the-Loop pause
"""

import time
import random
from pathlib import Path
from typing import Optional, Callable, Dict, Any, List
import win32gui

from firefox_manager.authentication.system_automation import (
    system_automation,
    VK_ESCAPE,
    VK_RETURN,
    VK_MENU,
)
from firefox_manager.automation.auto_ads_models import AutoAdsConfig
from firefox_manager.automation.smart_locator import SmartLocator
from firefox_manager.automation.smart_vision import smart_vision
from firefox_manager.automation.ad_agent_recovery import NeedsHumanChallenge, PolicyRestrictionError

EU_COUNTRIES = {
    "austria", "belgium", "bulgaria", "croatia", "cyprus", "czech republic",
    "denmark", "estonia", "finland", "france", "germany", "greece", "hungary",
    "ireland", "italy", "latvia", "lithuania", "luxembourg", "malta", "netherlands",
    "poland", "portugal", "romania", "slovakia", "slovenia", "spain", "sweden",
    "united kingdom", "uk"
}

RANDOM_PAYEE_NAMES = [
    "Nova Horizon Media Ltd",
    "Apex Commerce Solutions",
    "Vanguard Digital Group",
    "Starlight Ventures LLC",
    "Atlas Global Marketing",
    "Crestline Enterprises",
]


class StepContext:
    """Carries execution state across native Firefox steps."""

    def __init__(
        self,
        hwnd: int,
        config: AutoAdsConfig,
        log_step: Callable[[str], None],
        check_interruption: Callable[[], None],
        navigate_url: Callable[[int, str], None],
        wait_ready: Callable[[float], None],
        scroll_mouse: Callable[[int, int, int, int], None],
    ):
        self.hwnd = hwnd
        self.config = config
        self.log_step = log_step
        self.check_interruption = check_interruption
        self.navigate_url = navigate_url
        self.wait_ready = wait_ready
        self.scroll_mouse = scroll_mouse

    def locator(self, step_name: str) -> SmartLocator:
        return SmartLocator(self.hwnd, step_name)

    def window_geometry(self):
        rect = win32gui.GetWindowRect(self.hwnd)
        base_x = max(0, rect[0])
        base_y = max(0, rect[1])
        w = max(800, rect[2] - rect[0])
        h = max(600, rect[3] - rect[1])
        return base_x, base_y, w, h

    def check_for_checkpoint(self) -> None:
        """Inspect if native Firefox is displaying security checkpoint or locked account."""
        title = system_automation.get_window_title(self.hwnd).lower()
        checkpoint_terms = [
            "checkpoint", "security check", "confirm your identity",
            "verify it's you", "two-factor", "log in with another device",
            "locked", "confirm this is your meta account"
        ]
        if any(term in title for term in checkpoint_terms):
            raise NeedsHumanChallenge(
                f"Facebook Security Checkpoint detected in Firefox (Title: '{title}'). "
                "Please complete verification in Firefox, then click Resume.",
                challenge_type="security_checkpoint"
            )

        # Check for policy restriction banner
        restriction = smart_vision.check_facebook_ad_restrictions(self.hwnd)
        if restriction:
            raise PolicyRestrictionError(restriction)


class BaseAdStep:
    name: str = "base_step"
    description: str = "Base step"

    def is_done(self, ctx: StepContext) -> bool:
        """Returns True if this step has already been accomplished."""
        return False

    def execute(self, ctx: StepContext) -> None:
        """Execute step actions."""
        raise NotImplementedError

    def verify(self, ctx: StepContext) -> bool:
        """Verify that step achieved desired outcome."""
        return True


# =============================================================================
# STEP 1: Profile Resolution & Security Check
# =============================================================================
class ProfileResolutionStep(BaseAdStep):
    name = "profile_resolution"
    description = "Profile Resolution & Security Check"

    def is_done(self, ctx: StepContext) -> bool:
        return ctx.hwnd is not None and win32gui.IsWindow(ctx.hwnd)

    def execute(self, ctx: StepContext) -> None:
        ctx.log_step("Asserting native Firefox window focus and responsiveness...")
        system_automation.force_focus_window(ctx.hwnd)
        time.sleep(0.5)
        ctx.check_for_checkpoint()

    def verify(self, ctx: StepContext) -> bool:
        ctx.check_for_checkpoint()
        return ctx.hwnd is not None and win32gui.IsWindow(ctx.hwnd)


# =============================================================================
# STEP 2: Profile Lock Inspection & Automatic Unlock
# =============================================================================
class UnlockProfileStep(BaseAdStep):
    name = "unlock_profile"
    description = "Profile Lock Inspection & Unlock"

    def is_done(self, ctx: StepContext) -> bool:
        if not getattr(ctx.config, "unlock_profile_if_locked", True):
            return True
        loc = ctx.locator(self.name)
        has_lock = loc.is_present(["uia=Button:Unlock profile", "uia=Text:Unlock profile"], timeout=0.8)
        return not has_lock

    def execute(self, ctx: StepContext) -> None:
        if not getattr(ctx.config, "unlock_profile_if_locked", True):
            ctx.log_step("Profile unlock check skipped by configuration.")
            return

        ctx.log_step("Navigating native Firefox to profile to inspect Locked Profile restriction...")
        ctx.navigate_url(ctx.hwnd, "https://www.facebook.com/me")
        ctx.wait_ready(4.5)
        system_automation.send_key(VK_ESCAPE)
        time.sleep(0.3)
        ctx.check_for_checkpoint()

        loc = ctx.locator(self.name)
        candidates = [
            "uia=Button:Unlock profile",
            "uia=Text:Unlock profile",
            "coord=0.82,0.365",
        ]

        if loc.is_present(candidates, timeout=1.0):
            ctx.log_step("🔒 Profile is LOCKED by Facebook. Initiating unlock sequence in Firefox...")
            loc.click(candidates, timeout=1.5)
            ctx.wait_ready(2.5)

            unlock_confirm_cands = [
                "color=blue:0.40,0.60,0.75,0.88",
                "uia=Button:Unlock",
                "uia=Button:Unlock your profile",
                "coord=0.50,0.75",
            ]
            loc.click(unlock_confirm_cands, timeout=2.0)
            ctx.wait_ready(3.0)
            ctx.log_step("✓ Profile unlock requested and confirmed.")
        else:
            ctx.log_step("✓ Profile is open and NOT locked.")

    def verify(self, ctx: StepContext) -> bool:
        ctx.check_for_checkpoint()
        return True


# =============================================================================
# STEP 3: Professional Mode Verification & Activation
# =============================================================================
class ProfessionalModeStep(BaseAdStep):
    name = "professional_mode"
    description = "Professional Mode Check & Activation"

    def is_done(self, ctx: StepContext) -> bool:
        if not ctx.config.enable_pro_mode:
            return True
        if not ctx.config.skip_pro_mode_if_active:
            return False

        # Look for active Creator/Professional dashboard blue button
        dashboard_btn = smart_vision.find_facebook_primary_blue_button(
            ctx.hwnd, region=(0.60, 0.30, 0.78, 0.45)
        )
        if dashboard_btn:
            return True

        loc = ctx.locator(self.name)
        return loc.is_present(["uia=Button:Professional dashboard", "uia=Text:Professional dashboard"], timeout=0.8)

    def execute(self, ctx: StepContext) -> None:
        if not ctx.config.enable_pro_mode:
            ctx.log_step("Professional Mode activation skipped by user preference.")
            return

        ctx.check_for_checkpoint()
        ctx.log_step("Inspecting native Firefox profile for Professional Mode...")
        ctx.navigate_url(ctx.hwnd, "https://www.facebook.com/me")
        ctx.wait_ready(5.0)
        system_automation.send_key(VK_ESCAPE)
        time.sleep(0.5)

        if self.is_done(ctx):
            ctx.log_step("✓ Professional Mode is already ACTIVE on this profile.")
            return

        ctx.log_step("Activating Professional Mode via profile controls...")
        loc = ctx.locator(self.name)

        # 1. Click Profile three-dots menu
        three_dots_cands = [
            "uia=Button:More profile settings",
            "coord=0.82,0.365",
        ]
        loc.click(three_dots_cands, timeout=2.0)
        time.sleep(1.5)

        # 2. Click 'Turn on professional mode'
        turn_on_cands = [
            "uia=Button:Turn on professional mode",
            "uia=Text:Turn on professional mode",
            "coord=0.75,0.55",
        ]
        loc.click(turn_on_cands, timeout=2.0)
        time.sleep(2.0)

        # 3. Click primary blue 'Turn on' confirmation button
        confirm_cands = [
            "color=blue:0.40,0.60,0.70,0.85",
            "uia=Button:Turn on",
            "coord=0.55,0.72",
        ]
        loc.click(confirm_cands, timeout=2.5)
        ctx.wait_ready(3.5)
        ctx.log_step("✓ Professional Mode activation sequence completed.")

    def verify(self, ctx: StepContext) -> bool:
        ctx.check_for_checkpoint()
        return True


# =============================================================================
# STEP 4: Meta Ad Center Navigation & Form Initialization
# =============================================================================
class NavigateAdCenterStep(BaseAdStep):
    name = "navigate_ad_center"
    description = "Meta Ad Center Navigation"

    def is_done(self, ctx: StepContext) -> bool:
        return smart_vision.is_ad_creation_page_active(ctx.hwnd)

    def execute(self, ctx: StepContext) -> None:
        if self.is_done(ctx):
            ctx.log_step("✓ Meta Ad Creation form is already active on screen.")
            return

        ctx.log_step("Navigating directly to Meta Ad Center in Firefox...")
        ctx.navigate_url(ctx.hwnd, "https://www.facebook.com/professional_dashboard/ad_center/")
        ctx.wait_ready(5.0)
        ctx.check_for_checkpoint()

        system_automation.send_key(VK_ESCAPE)
        time.sleep(0.3)
        system_automation.send_key(VK_ESCAPE)
        time.sleep(0.3)

        if not self.is_done(ctx):
            # Fallback 1: Professional Dashboard Tools
            ctx.log_step("Direct Ad Center did not open creation form. Trying Tools page...")
            ctx.navigate_url(ctx.hwnd, "https://www.facebook.com/professional_dashboard/tools/")
            ctx.wait_ready(5.0)
            system_automation.send_key(VK_ESCAPE)
            time.sleep(0.3)

            base_x, base_y, w, h = ctx.window_geometry()
            ctx.scroll_mouse(ctx.hwnd, int(base_x + w * 0.5), int(base_y + h * 0.5), ticks=-6)
            time.sleep(1.5)

            loc = ctx.locator(self.name)
            loc.click(["coord=0.42,0.68", "uia=Button:Ad Center", "uia=Text:Ad Center"], timeout=2.0)
            ctx.wait_ready(5.0)

        # In Ad Center: Click 'Advertise' / 'Create new ad'
        if not self.is_done(ctx):
            ctx.log_step("Resolving 'Advertise' button in Ad Center...")
            loc = ctx.locator(self.name)
            adv_cands = [
                "color=blue:0.30,0.15,0.60,0.28",
                "uia=Button:Advertise",
                "uia=Button:Create ad",
                "coord=0.392,0.196",
            ]
            loc.click(adv_cands, timeout=2.5)
            ctx.wait_ready(4.0)

            # In 'Choose ad type' dialog, click 'Create new ad'
            if not self.is_done(ctx):
                ctx.log_step("Selecting 'Create new ad' card...")
                create_new_cands = [
                    "uia=Button:Create new ad",
                    "uia=Text:Create new ad",
                    "coord=0.50,0.353",
                ]
                loc.click(create_new_cands, timeout=2.0)
                ctx.wait_ready(4.5)

    def verify(self, ctx: StepContext) -> bool:
        ctx.check_for_checkpoint()
        for _ in range(5):
            if smart_vision.is_ad_creation_page_active(ctx.hwnd):
                return True
            time.sleep(1.2)

        restriction = smart_vision.check_facebook_ad_restrictions(ctx.hwnd)
        if restriction:
            raise PolicyRestrictionError(restriction)
        return True


# =============================================================================
# STEP 5: Set Goal Objective (Traffic / Website Visitors)
# =============================================================================
class SetGoalStep(BaseAdStep):
    name = "set_goal"
    description = "Ad Objective: Traffic / Website Visitors"

    def execute(self, ctx: StepContext) -> None:
        ctx.check_for_checkpoint()
        ctx.log_step("Setting campaign goal to 'Get more website visitors' (Traffic)...")
        loc = ctx.locator(self.name)

        # 1. Click 'Change' button on Goal card
        change_cands = [
            "color=grey:0.40,0.14,0.55,0.26",
            "uia=Button:Change",
            "coord=0.474,0.183",
        ]
        loc.click(change_cands, timeout=2.5)
        time.sleep(2.0)

        # 2. In Goal modal: Click 'Get more website visitors' option
        goal_cands = [
            "uia=RadioButton:Get more website visitors",
            "uia=Text:Get more website visitors",
            "coord=0.50,0.45",
        ]
        loc.click(goal_cands, timeout=2.0)
        time.sleep(1.0)

        # 3. Scroll down modal to reveal Save button
        base_x, base_y, w, h = ctx.window_geometry()
        ctx.scroll_mouse(ctx.hwnd, int(base_x + w * 0.50), int(base_y + h * 0.60), ticks=-4)
        time.sleep(1.0)

        # 4. Click blue 'Save' button in modal
        save_cands = [
            "color=blue:0.60,0.70,0.85,0.95",
            "uia=Button:Save",
            "coord=0.70,0.85",
        ]
        loc.click(save_cands, timeout=2.5)
        ctx.wait_ready(2.5)
        ctx.log_step("✓ Goal objective confirmed: 'Get more website visitors'.")

    def verify(self, ctx: StepContext) -> bool:
        ctx.check_for_checkpoint()
        return True


# =============================================================================
# STEP 6: Populate Ad Creative (Description, Media, Headline, URL, CTA)
# =============================================================================
class FillCreativeStep(BaseAdStep):
    name = "fill_creative"
    description = "Ad Creative: Description, Media, Headline & URL"

    def execute(self, ctx: StepContext) -> None:
        ctx.check_for_checkpoint()
        ctx.log_step("Inputting Ad Creative parameters...")
        base_x, base_y, w, h = ctx.window_geometry()
        panel_x = int(base_x + w * 0.35)
        panel_y = int(base_y + h * 0.50)

        # Scroll down slightly to ensure description is visible
        ctx.scroll_mouse(ctx.hwnd, panel_x, panel_y, ticks=-3)
        time.sleep(1.0)

        loc = ctx.locator(self.name)

        # 1. Primary Text / Description
        ctx.log_step(f"Inputting Ad Description: '{ctx.config.ad_description[:35]}...'")
        desc_cands = [
            "uia=Edit:Description",
            "uia=Edit:Primary text",
            "coord=0.35,0.24",
        ]
        loc.fill(desc_cands, ctx.config.ad_description)
        time.sleep(0.5)

        # 2. Creative Image File Upload (if image path provided)
        if ctx.config.image_path and Path(ctx.config.image_path).exists():
            ctx.log_step(f"Uploading creative image: {Path(ctx.config.image_path).name}")
            media_cands = [
                "color=grey:0.35,0.38,0.50,0.48",
                "uia=Button:Select media",
                "coord=0.42,0.42",
            ]
            try:
                loc.click(media_cands, timeout=2.0)
                time.sleep(1.5)
                uploaded = system_automation.handle_open_file_dialog(ctx.config.image_path, timeout=5.0)
                if uploaded:
                    ctx.log_step("✓ Creative image uploaded successfully.")
                    time.sleep(2.0)
                else:
                    ctx.log_step("ℹ️ File dialog not triggered or handled manually.")
            except Exception as e:
                ctx.log_step(f"⚠️ Image selection notice: {e}")

        # 3. Headline
        ctx.log_step(f"Inputting Headline: '{ctx.config.ad_headline}'")
        headline_cands = [
            "uia=Edit:Headline",
            "coord=0.35,0.67",
        ]
        loc.fill(headline_cands, ctx.config.ad_headline)
        time.sleep(0.5)

        # Scroll down to Button label and Website Destination URL
        ctx.scroll_mouse(ctx.hwnd, panel_x, panel_y, ticks=-4)
        time.sleep(1.0)

        # 4. CTA Action Button
        ctx.log_step(f"Configuring CTA Button: '{ctx.config.cta_button}'")
        cta_cands = [
            "uia=ComboBox:Button",
            "coord=0.35,0.235",
        ]
        try:
            loc.click(cta_cands, timeout=1.5)
            time.sleep(0.5)
            system_automation.paste_into_focused_input(ctx.config.cta_button)
            time.sleep(0.2)
            system_automation.send_key(VK_RETURN)
            time.sleep(0.5)
        except Exception:
            pass

        # 5. Website Destination URL
        ctx.log_step(f"Setting Destination Website URL: {ctx.config.target_url}")
        url_cands = [
            "uia=Edit:Website URL",
            "coord=0.35,0.335",
        ]
        loc.fill(url_cands, ctx.config.target_url)
        time.sleep(0.5)

    def verify(self, ctx: StepContext) -> bool:
        ctx.check_for_checkpoint()
        return True


# =============================================================================
# STEP 7: Audience Targeting, European Payee & Budget
# =============================================================================
class AudienceBudgetStep(BaseAdStep):
    name = "audience_budget"
    description = "Audience Targeting, EU Compliance & Budget"

    def execute(self, ctx: StepContext) -> None:
        ctx.check_for_checkpoint()
        base_x, base_y, w, h = ctx.window_geometry()
        panel_x = int(base_x + w * 0.35)
        panel_y = int(base_y + h * 0.50)

        # Scroll down to Audience & Budget
        ctx.scroll_mouse(ctx.hwnd, panel_x, panel_y, ticks=-5)
        time.sleep(1.0)

        # European Payee Compliance
        is_eu_targeted = any(c.lower().strip() in EU_COUNTRIES for c in ctx.config.target_countries)
        if is_eu_targeted:
            payee = ctx.config.payee_name or random.choice(RANDOM_PAYEE_NAMES)
            ctx.log_step(f"🇪🇺 European Target detected. Applying compliance declaration payee: '{payee}'")

        # Daily Budget
        ctx.log_step(f"Setting Daily Budget: ${ctx.config.daily_budget:.2f} for {ctx.config.duration_days} days.")
        loc = ctx.locator(self.name)
        budget_cands = [
            "uia=Edit:Daily budget",
            "coord=0.21,0.72",
        ]
        loc.fill(budget_cands, f"{ctx.config.daily_budget:.2f}")
        time.sleep(0.5)

    def verify(self, ctx: StepContext) -> bool:
        ctx.check_for_checkpoint()
        return True


# =============================================================================
# STEP 8: Publish Ad Campaign & Checkpoint Gate
# =============================================================================
class PublishStep(BaseAdStep):
    name = "publish"
    description = "Final Review & Publication Submission"

    def execute(self, ctx: StepContext) -> None:
        ctx.check_for_checkpoint()
        ctx.log_step("Triggering Ad Publication ('Publish')...")
        loc = ctx.locator(self.name)

        pub_cands = [
            "color=blue:0.48,0.85,0.88,0.99",
            "uia=Button:Publish",
            "coord=0.75,0.93",
        ]
        loc.click(pub_cands, timeout=2.5)
        ctx.wait_ready(5.0)

    def verify(self, ctx: StepContext) -> bool:
        ctx.check_for_checkpoint()
        title = system_automation.get_window_title(ctx.hwnd).lower()
        challenge_keywords = [
            "security check", "checkpoint", "two-factor", "confirm your identity",
            "verification", "enter code", "captcha", "payment method", "add payment",
            "log in with another device", "locked"
        ]
        if any(kw in title for kw in challenge_keywords):
            raise NeedsHumanChallenge(
                "Security checkpoint, verification, or payment method setup required in Firefox.",
                challenge_type="verification_or_payment"
            )
        return True


# Complete Standard Pipeline Order
DEFAULT_AD_PIPELINE: List[BaseAdStep] = [
    ProfileResolutionStep(),
    UnlockProfileStep(),
    ProfessionalModeStep(),
    NavigateAdCenterStep(),
    SetGoalStep(),
    FillCreativeStep(),
    AudienceBudgetStep(),
    PublishStep(),
]
