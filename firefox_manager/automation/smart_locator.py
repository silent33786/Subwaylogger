"""
Native Firefox Smart Element Locator with Self-Learning Memory.
Works with 100% untouched native Firefox profiles:
1. SmartVision computer-vision color cluster recognition (Primary Blue & Secondary Grey buttons)
2. UIAutomation accessibility element inspection
3. Standardized maximized window layout anchors
All candidate strategies are ranked dynamically per step by historical success rate.
"""

import time
import logging
from typing import Optional, Tuple, List, Dict, Any
import win32gui

from firefox_manager.authentication.system_automation import (
    system_automation,
    VK_RETURN,
    VK_TAB,
    VK_ESCAPE,
)
from firefox_manager.automation.ad_agent_memory import agent_memory
from firefox_manager.automation.smart_vision import smart_vision

logger = logging.getLogger("NativeSmartLocator")


class SmartLocator:
    """
    Adaptive element locator for native Firefox that tries multiple strategies
    in order of learned performance.
    """

    def __init__(self, hwnd: int, step_name: str):
        self.hwnd = hwnd
        self.step_name = step_name

    def _get_window_geometry(self) -> Tuple[int, int, int, int]:
        """Obtain current window left, top, width, height."""
        rect = win32gui.GetWindowRect(self.hwnd)
        base_x = max(0, rect[0])
        base_y = max(0, rect[1])
        w = max(800, rect[2] - rect[0])
        h = max(600, rect[3] - rect[1])
        return base_x, base_y, w, h

    def _resolve_candidate(self, cand: str, timeout: float = 1.0) -> Optional[Tuple[int, int]]:
        """
        Attempt to resolve a candidate descriptor to screen coordinates (x, y).
        - 'color=blue:0.4,0.6,0.7,0.85' -> Primary blue button search via computer vision
        - 'color=grey:0.4,0.14,0.55,0.26' -> Secondary grey button search
        - 'uia=Button:Turn on' -> UIAutomation search
        - 'coord=0.82,0.365' -> Maximized window relative ratio
        """
        base_x, base_y, w, h = self._get_window_geometry()

        # 1. Color button locator (SmartVision pixel recognition)
        if cand.startswith("color="):
            rest = cand[6:]
            color_type, region_str = rest.split(":", 1) if ":" in rest else (rest, None)
            region = None
            if region_str:
                rparts = [float(p) for p in region_str.split(",")]
                if len(rparts) == 4:
                    region = (rparts[0], rparts[1], rparts[2], rparts[3])

            if color_type == "blue":
                pt = smart_vision.find_facebook_primary_blue_button(self.hwnd, region=region)
                if pt:
                    return pt
            elif color_type == "grey":
                pt = smart_vision.find_facebook_secondary_grey_button(self.hwnd, region=region)
                if pt:
                    return pt

        # 2. UIAutomation candidate
        if cand.startswith("uia="):
            spec = cand[4:]
            ctrl_type, title = spec.split(":", 1) if ":" in spec else ("Button", spec)
            try:
                import pywinauto
                app = pywinauto.Desktop(backend="uia")
                win = app.window(handle=self.hwnd)
                ctrl = win.child_window(title_re=f".*{title}.*", control_type=ctrl_type)
                if ctrl.exists(timeout=timeout):
                    rect = ctrl.rectangle()
                    cx = int((rect.left + rect.right) / 2)
                    cy = int((rect.top + rect.bottom) / 2)
                    return (cx, cy)
            except Exception:
                pass

        # 3. Normalized coordinate ratio anchor on maximized window
        if cand.startswith("coord="):
            parts = cand[6:].split(",")
            if len(parts) == 2:
                rx, ry = float(parts[0]), float(parts[1])
                x = int(base_x + w * rx)
                y = int(base_y + h * ry)
                return (x, y)

        return None

    def find(self, candidates: List[str], timeout: float = 1.5) -> Tuple[Tuple[int, int], str]:
        """
        Iterate over ranked candidates. Return (screen_coordinates, winning_candidate_string).
        """
        ranked_candidates = agent_memory.rank(self.step_name, candidates)
        last_err = None

        for cand in ranked_candidates:
            key = f"{self.step_name}|{cand}"
            try:
                coords = self._resolve_candidate(cand, timeout=timeout)
                if coords:
                    agent_memory.record(key, True)
                    return coords, cand
                else:
                    agent_memory.record(key, False)
            except Exception as e:
                agent_memory.record(key, False)
                last_err = e

        raise TimeoutError(
            f"[{self.step_name}] No locator candidates resolved: {candidates}. Last error: {last_err}"
        )

    def is_present(self, candidates: List[str], timeout: float = 0.8) -> bool:
        """Check if any candidate selector resolves."""
        try:
            self.find(candidates, timeout=timeout)
            return True
        except Exception:
            return False

    def click(self, candidates: List[str], timeout: float = 1.5, pre_delay: float = 0.2, post_delay: float = 0.5) -> str:
        """Find and left-click the first matching candidate."""
        coords, winning_cand = self.find(candidates, timeout=timeout)
        time.sleep(pre_delay)
        system_automation.force_focus_window(self.hwnd)
        system_automation.mouse_click(coords[0], coords[1])
        time.sleep(post_delay)
        return winning_cand

    def double_click(self, candidates: List[str], timeout: float = 1.5) -> str:
        """Find and double-click to focus field."""
        coords, winning_cand = self.find(candidates, timeout=timeout)
        system_automation.force_focus_window(self.hwnd)
        system_automation.mouse_double_click(coords[0], coords[1])
        time.sleep(0.3)
        return winning_cand

    def fill(
        self,
        candidates: List[str],
        value: str,
        clear_first: bool = True,
        timeout: float = 1.5,
    ) -> str:
        """Focus an input field, safely clear it, and paste value via OS clipboard."""
        coords, winning_cand = self.find(candidates, timeout=timeout)
        system_automation.force_focus_window(self.hwnd)
        system_automation.mouse_double_click(coords[0], coords[1])
        time.sleep(0.25)

        if clear_first:
            system_automation.safe_clear_focused_input()
            time.sleep(0.15)

        system_automation.paste_into_focused_input(str(value))
        time.sleep(0.3)
        return winning_cand
