"""
Native Firefox Diagnostic, Classification, and Adaptive Recovery Engine.
Features:
1. Precise error classification (Security Checkpoint, CAPTCHA, Account Locked, Logged Out, Policy Restrictions)
2. Human-in-the-Loop challenge interception (NeedsHumanChallenge)
3. High-resolution diagnostic screenshot capture of native window
4. Self-learning ranked recovery routines (popup dismissal, overlay escape, scroll, reload)
"""

import time
import logging
from pathlib import Path
from typing import Optional, Callable, Dict, Any, List
import win32gui

from firefox_manager.config.settings import settings
from firefox_manager.authentication.system_automation import (
    system_automation,
    VK_ESCAPE,
    VK_RETURN,
)
from firefox_manager.automation.ad_agent_memory import agent_memory
from firefox_manager.automation.smart_vision import smart_vision

logger = logging.getLogger("NativeFirefoxRecovery")


class NeedsHumanChallenge(Exception):
    """
    Raised when a security checkpoint, 2FA prompt, CAPTCHA, or payment setup
    requires human verification. Automation pauses safely without blind actions.
    """
    def __init__(self, message: str, challenge_type: str = "security"):
        super().__init__(message)
        self.challenge_type = challenge_type


class PolicyRestrictionError(Exception):
    """Raised when Meta advertising restrictions or policy rejections are detected."""
    pass


class AdAgentRecovery:
    """Intelligent recovery manager that diagnoses and resolves native browser hurdles."""

    def __init__(self):
        data_dir = getattr(settings, "data_dir", Path("data"))
        self.shot_dir = Path(data_dir) / "agent_shots"
        self.shot_dir.mkdir(parents=True, exist_ok=True)

    def capture_diagnostic_shot(self, hwnd: Optional[int], tag: str) -> Optional[Path]:
        """Capture a timestamped diagnostic screenshot of the native Firefox window."""
        if not hwnd:
            return None
        try:
            timestamp = int(time.time())
            clean_tag = "".join(c if c.isalnum() or c in ("-", "_") else "_" for c in tag)
            path = self.shot_dir / f"{timestamp}_{clean_tag}.png"
            img = smart_vision.capture_window_image(hwnd)
            if img:
                img.save(str(path))
                logger.info(f"Diagnostic screenshot saved to {path}")
                return path
        except Exception as e:
            logger.warning(f"Failed to capture diagnostic screenshot: {e}")
        return None

    def classify_failure(self, hwnd: Optional[int], err: Exception) -> str:
        """
        Analyze current window title and exception message to classify the problem.
        Categories:
        - 'security': Checkpoint, CAPTCHA, 2FA, Identity Verification, Account Locked
        - 'payment_required': Missing payment method prompt
        - 'ad_restricted': Account or Ad policy rejection
        - 'logged_out': Session expired or login screen
        - 'element_missing': Missing DOM element or timeout
        - 'unknown': Unrecognized error
        """
        title = ""
        try:
            if hwnd:
                title = system_automation.get_window_title(hwnd).lower()
        except Exception:
            pass

        err_str = str(err).lower()
        combined = f"{title} {err_str}"

        # 1. Security Checkpoint / 2FA / Account Locked
        security_terms = [
            "checkpoint", "captcha", "security check", "confirm your identity",
            "verify it's you", "enter code", "help us confirm", "two-factor",
            "security code", "phone verification", "upload an id",
            "your account was locked", "confirm this is your meta account",
            "log in with another device", "locked"
        ]
        if any(term in combined for term in security_terms):
            return "security"

        # 2. Payment Method Block
        payment_terms = ["add payment method", "payment required", "set up payment", "enter payment info"]
        if any(term in combined for term in payment_terms):
            return "payment_required"

        # 3. Logged Out / Session Expired
        login_terms = ["log in to facebook", "login.php", "session expired", "please log in"]
        if any(term in combined for term in login_terms):
            return "logged_out"

        # 4. Ad Policy Restrictions
        restriction_terms = ["account restricted", "advertising access restricted", "we rejected your ad"]
        if any(term in combined for term in restriction_terms):
            return "ad_restricted"

        # 5. Missing Element / Timeout
        if "timeout" in err_str or "not found" in err_str or "verify fail" in err_str or "no locator" in err_str:
            return "element_missing"

        return "unknown"

    # =========================================================================
    # RECOVERY ACTIONS
    # =========================================================================

    def dismiss_popups(self, hwnd: int, log_step: Optional[Callable[[str], None]] = None) -> bool:
        """Dismiss common Facebook modal dialogues, cookies, or 'Not now' prompts in Firefox."""
        if log_step:
            log_step("🛡️ Recovery: Attempting to dismiss modal popups and overlays in Firefox...")

        system_automation.force_focus_window(hwnd)
        system_automation.send_key(VK_ESCAPE)
        time.sleep(0.3)

        # Look for secondary grey button
        grey_btn = smart_vision.find_facebook_secondary_grey_button(
            hwnd, region=(0.40, 0.40, 0.70, 0.85)
        )
        if grey_btn:
            system_automation.mouse_click(grey_btn[0], grey_btn[1])
            time.sleep(0.5)
            return True
        return False

    def escape_overlay(self, hwnd: int, log_step: Optional[Callable[[str], None]] = None) -> bool:
        """Send Escape key to clear open dropdowns or floating modals."""
        if log_step:
            log_step("🛡️ Recovery: Sending ESC keys to clear active overlays in Firefox...")
        system_automation.force_focus_window(hwnd)
        system_automation.send_key(VK_ESCAPE)
        time.sleep(0.3)
        system_automation.send_key(VK_ESCAPE)
        time.sleep(0.5)
        return True

    def scroll_down(self, hwnd: int, log_step: Optional[Callable[[str], None]] = None) -> bool:
        """Scroll down smoothly to reveal off-screen form inputs."""
        if log_step:
            log_step("🛡️ Recovery: Scrolling Firefox viewport down...")
        rect = win32gui.GetWindowRect(hwnd)
        cx = int((rect[0] + rect[2]) / 2)
        cy = int((rect[1] + rect[3]) / 2)
        system_automation.force_focus_window(hwnd)
        system_automation.user32.SetCursorPos(cx, cy)
        time.sleep(0.1)
        for _ in range(5):
            system_automation.user32.mouse_event(0x0800, 0, 0, -120, 0)
            time.sleep(0.08)
        time.sleep(0.6)
        return True

    def scroll_up(self, hwnd: int, log_step: Optional[Callable[[str], None]] = None) -> bool:
        """Scroll up smoothly."""
        if log_step:
            log_step("🛡️ Recovery: Scrolling Firefox viewport up...")
        rect = win32gui.GetWindowRect(hwnd)
        cx = int((rect[0] + rect[2]) / 2)
        cy = int((rect[1] + rect[3]) / 2)
        system_automation.force_focus_window(hwnd)
        system_automation.user32.SetCursorPos(cx, cy)
        time.sleep(0.1)
        for _ in range(5):
            system_automation.user32.mouse_event(0x0800, 0, 0, 120, 0)
            time.sleep(0.08)
        time.sleep(0.6)
        return True

    def wait_and_rehydrate(self, hwnd: int, log_step: Optional[Callable[[str], None]] = None) -> bool:
        """Allow extra time for page dynamic components to mount."""
        if log_step:
            log_step("🛡️ Recovery: Waiting 3.5s for dynamic DOM rehydration...")
        time.sleep(3.5)
        return True

    def reload_page(self, hwnd: int, log_step: Optional[Callable[[str], None]] = None) -> bool:
        """Reload page in Firefox."""
        if log_step:
            log_step("🛡️ Recovery: Reloading active webpage via F5...")
        system_automation.force_focus_window(hwnd)
        system_automation.send_key(0x74)  # VK_F5
        time.sleep(4.0)
        return True

    def get_all_recovery_actions(self) -> Dict[str, Callable]:
        """Dictionary of all available recovery routines."""
        return {
            "dismiss_popups": self.dismiss_popups,
            "escape_overlay": self.escape_overlay,
            "scroll_down": self.scroll_down,
            "scroll_up": self.scroll_up,
            "wait_and_rehydrate": self.wait_and_rehydrate,
            "reload_page": self.reload_page,
        }

    def execute_ranked_recovery(
        self,
        step_name: str,
        hwnd: int,
        attempt: int,
        log_step: Optional[Callable[[str], None]] = None,
    ) -> str:
        """
        Select and execute the highest-scoring recovery routine for this step from learned memory.
        """
        all_fixes = self.get_all_recovery_actions()
        scope = f"fix|{step_name}"
        ranked = agent_memory.rank(scope, list(all_fixes.keys()))

        idx = (attempt - 1) % len(ranked)
        chosen_fix = ranked[idx]

        score = agent_memory.score(f"{scope}|{chosen_fix}")
        if log_step:
            log_step(
                f"🔧 Applying learned recovery '{chosen_fix}' (Success score: {score:.2f}, Rank #{idx + 1})..."
            )

        fn = all_fixes[chosen_fix]
        try:
            fn(hwnd=hwnd, log_step=log_step)
        except Exception as e:
            logger.warning(f"Recovery fix '{chosen_fix}' encountered error: {e}")

        return chosen_fix


# Global recovery instance
agent_recovery = AdAgentRecovery()
