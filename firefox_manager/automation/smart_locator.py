"""
Native Firefox Smart Element Locator with Self-Learning Memory.
Works with 100% untouched native Firefox profiles:
1. SmartVision computer-vision color cluster recognition (Primary Blue & Secondary Grey buttons)
2. UIAutomation accessibility element inspection
3. Standardized maximized window layout anchors (LAST RESORT ONLY)

Coordinate candidates are never an auto-success: they are tried only
after every colour/UIA candidate has failed, and the caller must still
verify the result after clicking. A coordinate always "resolves", so
treating it as a found element used to click blindly at the wrong place.
All candidate strategies are ranked dynamically per step by historical success rate.
"""

import re
import time
import logging
from typing import Optional, Tuple, List, Dict, Any

try:
    import win32gui
except ImportError:  # pywin32 not installed / not Windows: guarded at call time.
    win32gui = None  # type: ignore[assignment]

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

    def _require_win32gui(self) -> None:
        if win32gui is None:
            raise RuntimeError(
                "SmartLocator needs Windows + pywin32 (pip install pywin32)."
            )

    def _get_window_geometry(self) -> Tuple[int, int, int, int]:
        """Obtain current window left, top, width, height."""
        self._require_win32gui()
        rect = win32gui.GetWindowRect(self.hwnd)
        base_x = max(0, rect[0])
        base_y = max(0, rect[1])
        w = max(800, rect[2] - rect[0])
        h = max(600, rect[3] - rect[1])
        return base_x, base_y, w, h

    def _resolve_candidate(
        self, cand: str, timeout: float = 1.0, deadline: Optional[float] = None
    ) -> Optional[Tuple[int, int]]:
        """
        Attempt to resolve a candidate descriptor to screen coordinates (x, y).
        - 'color=blue:0.4,0.6,0.7,0.85' -> Primary blue button search via computer vision
        - 'color=grey:0.4,0.14,0.55,0.26' -> Secondary grey button search
        - 'uia=Button:Turn on' -> UIAutomation search
        - 'coord=0.82,0.365' -> Maximized window relative ratio (last resort only;
          handled by find(), never here on its own)
        """
        if cand.startswith("coord="):
            # Coordinates are not resolved by this method. find() handles
            # them separately, only after all real candidates failed.
            return None

        # 1. Color button locator (SmartVision pixel recognition)
        if cand.startswith("color="):
            if deadline is not None and time.monotonic() > deadline:
                return None
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
                # Escape regex metacharacters in the title: the old code
                # interpolated the raw title into title_re, so a title
                # containing e.g. '(' or '+' either broke matching or
                # matched the wrong control.
                ctrl = win.child_window(
                    title_re=f".*{re.escape(title)}.*", control_type=ctrl_type
                )
                if ctrl.exists(timeout=timeout):
                    rect = ctrl.rectangle()
                    cx = int((rect.left + rect.right) / 2)
                    cy = int((rect.top + rect.bottom) / 2)
                    return (cx, cy)
            except Exception:
                pass

        return None

    def _resolve_coord(self, cand: str) -> Optional[Tuple[int, int]]:
        """Resolve a coord= candidate. Only called as a last resort by find()."""
        if not cand.startswith("coord="):
            return None
        base_x, base_y, w, h = self._get_window_geometry()
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

        Colour/UIA candidates are tried first, within the timeout.
        coord= candidates are tried LAST and only if no real candidate
        resolved. A coord win is still returned, but callers must verify
        after clicking - it proves nothing about what is on screen.
        """
        deadline = time.monotonic() + max(0.1, timeout)
        ranked_candidates = agent_memory.rank(self.step_name, candidates)
        last_err = None

        # Pass 1: real (colour / UIA) candidates, respecting the timeout.
        coord_candidates: List[str] = []
        for cand in ranked_candidates:
            if cand.startswith("coord="):
                coord_candidates.append(cand)
                continue
            key = f"{self.step_name}|{cand}"
            try:
                coords = self._resolve_candidate(cand, timeout=timeout, deadline=deadline)
                if coords:
                    agent_memory.record(key, True)
                    return coords, cand
                agent_memory.record(key, False)
            except Exception as e:
                agent_memory.record(key, False)
                last_err = e
            if time.monotonic() > deadline:
                break

        # Pass 2 (last resort only): coordinates. These always "resolve",
        # so they must never shadow a real candidate or mask a failure.
        for cand in coord_candidates:
            key = f"{self.step_name}|{cand}"
            try:
                coords = self._resolve_coord(cand)
                if coords:
                    logger.warning(
                        "[%s] No colour/UIA candidate resolved; falling back to "
                        "last-resort coordinates %s - caller must verify after clicking.",
                        self.step_name, cand,
                    )
                    agent_memory.record(key, True)
                    return coords, cand
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
