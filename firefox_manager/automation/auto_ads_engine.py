"""
Enterprise Facebook Auto Ads & Professional Mode Orchestration Engine.
Pure Native Firefox Execution:
- 100% Native untouched Firefox profiles launched via ProfileManager.
- ZERO external browser switching (NO Chromium, NO device tampering).
- Automatic window maximization (SW_MAXIMIZE) for consistent, uniform layout across all profiles.
- SmartVision pixel-accurate color button locator (Primary Blue & Secondary Grey buttons).
- Keyboard-driven universal focus & clipboard paste (Alt+D, Ctrl+F, Tab, Enter).
- Early Security Checkpoint interception with Human-in-the-Loop protocol.
- Persistent self-learning memory tracking (Bayesian Laplace ranking).
"""

import time
import logging
from typing import Optional, Callable, Dict, Any, List
from pathlib import Path
import win32gui
import win32con

from firefox_manager.config.settings import settings
from firefox_manager.database.database import db
from firefox_manager.core.profile_manager import profile_manager
from firefox_manager.core.process_manager import process_manager
from firefox_manager.security.audit_logger import audit_logger
from firefox_manager.authentication.system_automation import (
    system_automation,
    VK_ESCAPE,
    VK_RETURN,
    VK_TAB,
    VK_CONTROL,
    VK_MENU,
)
from firefox_manager.automation.auto_ads_models import AutoAdsConfig
from firefox_manager.automation.smart_vision import smart_vision
from firefox_manager.automation.profile_logger import profile_logger
from firefox_manager.automation.ad_agent_memory import agent_memory
from firefox_manager.automation.ad_agent_recovery import (
    agent_recovery,
    NeedsHumanChallenge,
    PolicyRestrictionError,
)
from firefox_manager.automation.ad_pipeline_steps import (
    DEFAULT_AD_PIPELINE,
    StepContext,
    BaseAdStep,
    EU_COUNTRIES,
    RANDOM_PAYEE_NAMES,
)

logger = logging.getLogger("AutoAdsEngine")


class FacebookAutoAdsEngine:
    """Enterprise self-learning Facebook Pro Mode & Ad Creation automation engine for native Firefox."""

    def __init__(self):
        self.is_paused = False
        self.should_stop = False
        self.current_hwnd: Optional[int] = None

    def pause(self) -> None:
        """Pause running automation gracefully."""
        self.is_paused = True

    def resume(self) -> None:
        """Resume paused automation."""
        self.is_paused = False

    def stop(self) -> None:
        """Abort running automation immediately."""
        self.should_stop = True
        self.is_paused = False

    def _check_interruption(self, log_step: Optional[Callable[[str], None]] = None) -> None:
        """Inspect pause and stop states at each execution phase."""
        if self.should_stop:
            raise InterruptedError("Auto Ads automation aborted by user.")

        paused_logged = False
        while self.is_paused:
            if not paused_logged:
                if log_step:
                    log_step("⏸️ Automation PAUSED. Waiting for user to resolve challenge in Firefox and click Resume...")
                paused_logged = True
            time.sleep(0.5)
            if self.should_stop:
                raise InterruptedError("Auto Ads automation aborted by user.")

        if paused_logged and log_step:
            log_step("▶️ Resuming Auto Ads execution...")

    def maximize_browser_window(self, hwnd: int) -> None:
        """
        Maximize Firefox window to ensure standard, consistent layout across all profiles.
        Eliminates variable window size bugs.
        """
        try:
            win32gui.ShowWindow(hwnd, win32con.SW_MAXIMIZE)
            time.sleep(0.5)
            system_automation.force_focus_window(hwnd)
            time.sleep(0.3)
        except Exception as e:
            logger.warning(f"Could not maximize Firefox window: {e}")

    def navigate_browser_to_url(self, hwnd: int, url: str) -> None:
        """
        Navigate native Firefox to a specific URL using Alt+D.
        Universal address bar focus shortcut that works from any DOM / dialog focus.
        """
        system_automation.force_focus_window(hwnd)
        time.sleep(0.3)

        # Alt+D focuses address bar in Firefox
        system_automation.user32.keybd_event(VK_MENU, 0, 0, 0)
        system_automation.user32.keybd_event(0x44, 0, 0, 0)  # 'D'
        time.sleep(0.06)
        system_automation.user32.keybd_event(0x44, 0, 2, 0)
        system_automation.user32.keybd_event(VK_MENU, 0, 2, 0)
        time.sleep(0.2)

        # Paste clean URL and hit Enter
        system_automation.paste_into_focused_input(url)
        time.sleep(0.2)
        system_automation.send_key(VK_RETURN)

    def wait_for_page_ready(
        self, seconds: float = 5.0, log_step: Optional[Callable[[str], None]] = None
    ) -> None:
        """Wait for page content to load while checking for stop/pause signals."""
        steps = int(seconds / 0.5)
        for _ in range(max(1, steps)):
            if log_step:
                self._check_interruption(log_step)
            time.sleep(0.5)

    def check_for_human_challenge(self, hwnd: int, log_step: Callable[[str], None]) -> bool:
        """
        Check if Facebook presents a CAPTCHA, 2FA, Phone Verification, or Checkpoint.
        If detected, brings native Firefox window to front for human resolution.
        """
        title = system_automation.get_window_title(hwnd).lower()
        challenge_keywords = [
            "security check", "checkpoint", "two-factor", "confirm your identity",
            "verification", "enter code", "captcha", "security code", "help us confirm",
            "phone number", "confirm phone", "payment method", "add payment",
            "log in with another device", "locked"
        ]

        if any(kw in title for kw in challenge_keywords):
            log_step("⚠️ Security Checkpoint / Verification detected in Firefox!")
            log_step("👉 Human-in-the-Loop: Native Firefox window brought to front. Please complete verification.")
            system_automation.force_focus_window(hwnd)
            agent_recovery.capture_diagnostic_shot(hwnd, "security_challenge")
            return True
        return False

    def scroll_mouse(self, hwnd: int, x_screen: int, y_screen: int, ticks: int) -> None:
        """Scroll mouse wheel up (positive ticks) or down (negative ticks)."""
        system_automation.force_focus_window(hwnd)
        system_automation.user32.SetCursorPos(x_screen, y_screen)
        time.sleep(0.15)
        delta = 120 if ticks > 0 else -120
        for _ in range(abs(ticks)):
            system_automation.user32.mouse_event(0x0800, 0, 0, delta, 0)
            time.sleep(0.08)
        time.sleep(0.4)

    def run_auto_ads_workflow(
        self,
        config: AutoAdsConfig,
        status_callback: Optional[Callable[[str], None]] = None,
        progress_callback: Optional[Callable[[int, int], None]] = None,
    ) -> Dict[str, Any]:
        """
        Main execution flow:
        Runs 100% native Firefox profile with auto-maximization,
        visual anchor detection, self-learning retry logic, and zero blind coordinate guessing.
        """
        self.is_paused = False
        self.should_stop = False

        def log_step(msg: str):
            if status_callback:
                status_callback(msg)
            profile_logger.log(config.profile_id, msg)
            audit_logger.log(
                agent_name="AutoAdsEngine",
                action="AUTO_ADS_STEP",
                target=config.profile_id,
                details=msg,
            )

        log_step(f"🚀 Initializing Native Firefox Auto Ads for Profile ID: {config.profile_id}")
        self._check_interruption(log_step)

        # 1. Resolve Profile Record
        profile = db.get_profile(config.profile_id)
        if not profile:
            raise ValueError(f"Profile '{config.profile_id}' not found.")

        # 2. Attach to existing or Launch dedicated Native Firefox Profile
        if process_manager.is_running(profile.id):
            pid = process_manager.get_pid(profile.id)
            process_manager.bring_to_front(profile.id)
            log_step(f"Attached to already running native Firefox instance (PID: {pid}).")
        else:
            log_step("Launching dedicated native Firefox profile...")
            pid = profile_manager.launch_profile(profile.id, initial_url="https://www.facebook.com/")
            self.wait_for_page_ready(6.0, log_step)

        hwnd = system_automation.find_firefox_window(target_pid=pid)
        if not hwnd:
            hwnd = system_automation.find_firefox_window()
        if not hwnd:
            raise RuntimeError("Could not find native Firefox window.")

        self.current_hwnd = hwnd

        # 3. Standardize Window Geometry: Maximize Firefox window
        log_step("Standardizing Firefox window geometry (Maximizing window)...")
        self.maximize_browser_window(hwnd)

        # 4. Check login session status
        sess_status = system_automation.check_facebook_session_status(profile.directory_name)
        if not sess_status.get("logged_in"):
            log_step("⚠️ Warning: Profile cookies do not show an active session. Proceeding with caution...")

        # 5. Construct execution context
        ctx = StepContext(
            hwnd=hwnd,
            config=config,
            log_step=log_step,
            check_interruption=lambda: self._check_interruption(log_step),
            navigate_url=self.navigate_browser_to_url,
            wait_ready=lambda sec: self.wait_for_page_ready(sec, log_step),
            scroll_mouse=self.scroll_mouse,
        )

        pipeline = DEFAULT_AD_PIPELINE
        total_steps = len(pipeline)

        for step_idx, step in enumerate(pipeline, start=1):
            if progress_callback:
                progress_callback(step_idx, total_steps)
            self._check_interruption(log_step)

            log_step(f"📌 Stage {step_idx}/{total_steps}: {step.description}")

            # Check for Security Checkpoint early
            try:
                ctx.check_for_checkpoint()
            except NeedsHumanChallenge as nhc:
                agent_recovery.capture_diagnostic_shot(hwnd, f"stage_{step_idx}_checkpoint")
                log_step(f"⚠️ {nhc}")
                log_step("👉 Native Firefox window is in front. Please complete verification in Firefox, then click Resume.")
                system_automation.force_focus_window(hwnd)
                self.pause()
                self._check_interruption(log_step)

            # Idempotency check: Skip if already done
            try:
                if step.is_done(ctx):
                    log_step(f"⏩ Stage {step_idx} ({step.name}) is already satisfied. Skipping...")
                    continue
            except Exception as e:
                logger.debug(f"is_done check for {step.name} returned error: {e}")

            # Execution loop with adaptive self-learning retries
            step_success = False
            last_fix: Optional[str] = None
            max_tries = getattr(config, "max_retries_per_step", 3)

            for attempt in range(1, max_tries + 1):
                self._check_interruption(log_step)
                try:
                    if attempt > 1:
                        log_step(f"🔄 Retrying {step.description} (Attempt {attempt}/{max_tries})...")

                    step.execute(ctx)

                    # Genuine verification
                    if step.verify(ctx):
                        if last_fix:
                            agent_memory.record(f"fix|{step.name}|{last_fix}", True)
                        step_success = True
                        log_step(f"✓ Stage {step_idx} ({step.description}) verified successfully.")
                        break
                    else:
                        raise RuntimeError(f"Verification check failed for stage '{step.name}'")

                except NeedsHumanChallenge as nhc:
                    if last_fix:
                        agent_memory.record(f"fix|{step.name}|{last_fix}", False)
                    agent_recovery.capture_diagnostic_shot(hwnd, f"{step.name}_human_challenge")
                    log_step(f"⚠️ Human Intervention Required: {nhc}")
                    log_step("👉 Native Firefox window is active. Please complete verification in Firefox and click Resume.")
                    system_automation.force_focus_window(hwnd)
                    self.pause()
                    self._check_interruption(log_step)
                    continue

                except PolicyRestrictionError as pre:
                    agent_recovery.capture_diagnostic_shot(hwnd, f"{step.name}_policy_restriction")
                    log_step(f"🚫 Meta Policy Restriction: {pre}")
                    log_step("👉 Automation paused for user review of policy flag in Firefox.")
                    system_automation.force_focus_window(hwnd)
                    self.pause()
                    self._check_interruption(log_step)
                    continue

                except Exception as err:
                    if last_fix:
                        agent_memory.record(f"fix|{step.name}|{last_fix}", False)

                    failure_kind = agent_recovery.classify_failure(hwnd, err)
                    if getattr(config, "diagnostic_screenshots", True):
                        shot_path = agent_recovery.capture_diagnostic_shot(hwnd, f"{step.name}_{failure_kind}")
                        if shot_path:
                            log_step(f"📸 Diagnostic snapshot saved: {shot_path.name}")

                    log_step(f"⚠️ Notice during {step.name} [{failure_kind}]: {str(err)[:120]}")

                    if failure_kind == "security":
                        log_step("🛡️ Security checkpoint detected. Bringing Firefox to front.")
                        system_automation.force_focus_window(hwnd)
                        self.pause()
                        self._check_interruption(log_step)
                        continue

                    if failure_kind == "logged_out":
                        raise RuntimeError(
                            f"Profile '{config.profile_id}' is logged out. Please log in inside Firefox."
                        )

                    # Apply learned recovery fix
                    if attempt < max_tries:
                        last_fix = agent_recovery.execute_ranked_recovery(
                            step_name=step.name,
                            hwnd=hwnd,
                            attempt=attempt,
                            log_step=log_step,
                        )

            if not step_success:
                raise RuntimeError(
                    f"Stage {step_idx} ({step.description}) failed after {max_tries} attempts. "
                    "Please check the Firefox window and diagnostic screenshots."
                )

        # Final Verification
        has_challenge = self.check_for_human_challenge(hwnd, log_step)
        mem_stats = agent_memory.get_stats()

        if has_challenge:
            log_step("⏳ Automation paused. Complete verification or payment setup in Firefox.")
            return {
                "success": True,
                "paused": True,
                "profile_id": config.profile_id,
                "message": "Ad submitted! Action required: Complete verification or payment in the open Firefox window.",
                "memory_stats": mem_stats,
            }

        log_step("🎉 Auto Ads execution finished successfully! All campaign parameters submitted.")
        return {
            "success": True,
            "profile_id": config.profile_id,
            "headline": config.ad_headline,
            "url": config.target_url,
            "budget": config.daily_budget,
            "message": "Auto Ads setup completed successfully.",
            "memory_stats": mem_stats,
        }


# Global engine instance
auto_ads_engine = FacebookAutoAdsEngine()
