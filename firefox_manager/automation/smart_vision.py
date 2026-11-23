"""
Smart Content & Visual Anchor Locator for Facebook Webpage Automation.
Provides robust recognition of buttons, modal dialogues, input fields, and text
without blind hardcoded coordinate guessing.
"""

import time
import ctypes
from ctypes import wintypes
from typing import Optional, Tuple, List, Dict, Any
from pathlib import Path
from PIL import Image
import win32gui
import win32service
import win32con

from firefox_manager.authentication.system_automation import system_automation, RECT


class SmartVisionLocator:
    """Intelligent visual and anchor-based locator for dynamic web layouts."""

    def __init__(self):
        self.user32 = ctypes.windll.user32
        self.gdi32 = ctypes.windll.gdi32

    def attach_to_desktop(self) -> None:
        """Ensure current thread is attached to interactive desktop."""
        try:
            desk = win32service.OpenInputDesktop(0, False, win32con.GENERIC_ALL)
            self.user32.SetThreadDesktop(int(desk))
        except Exception:
            pass

    def capture_window_image(self, hwnd: int) -> Optional[Image.Image]:
        """Capture live pixels of the given window handle with multi-monitor / desktop support."""
        if not hwnd or not self.user32:
            return None

        self.attach_to_desktop()

        rect = RECT()
        self.user32.GetWindowRect(ctypes.wintypes.HWND(hwnd), ctypes.byref(rect))
        w = max(10, rect.right - rect.left)
        h = max(10, rect.bottom - rect.top)

        hdc_win = self.user32.GetWindowDC(ctypes.wintypes.HWND(hwnd))
        if not hdc_win:
            return None

        hdc_mem = self.gdi32.CreateCompatibleDC(hdc_win)
        hbm = self.gdi32.CreateCompatibleBitmap(hdc_win, w, h)
        self.gdi32.SelectObject(hdc_mem, hbm)

        # PW_RENDERFULLCONTENT = 2
        self.user32.PrintWindow(ctypes.wintypes.HWND(hwnd), hdc_mem, 2)

        from ctypes import wintypes
        class BITMAPINFOHEADER(ctypes.Structure):
            _fields_ = [
                ('biSize', wintypes.DWORD), ('biWidth', wintypes.LONG), ('biHeight', wintypes.LONG),
                ('biPlanes', wintypes.WORD), ('biBitCount', wintypes.WORD), ('biCompression', wintypes.DWORD),
                ('biSizeImage', wintypes.DWORD), ('biXPelsPerMeter', wintypes.LONG), ('biYPelsPerMeter', wintypes.LONG),
                ('biClrUsed', wintypes.DWORD), ('biClrImportant', wintypes.DWORD)
            ]

        bmi = BITMAPINFOHEADER()
        bmi.biSize = ctypes.sizeof(BITMAPINFOHEADER)
        bmi.biWidth = w
        bmi.biHeight = -h  # Top-down
        bmi.biPlanes = 1
        bmi.biBitCount = 32
        bmi.biCompression = 0

        buffer = ctypes.create_string_buffer(w * h * 4)
        self.gdi32.GetDIBits(hdc_mem, hbm, 0, h, buffer, ctypes.byref(bmi), 0)

        self.gdi32.DeleteObject(hbm)
        self.gdi32.DeleteDC(hdc_mem)
        self.user32.ReleaseDC(ctypes.wintypes.HWND(hwnd), hdc_win)

        try:
            im = Image.frombuffer("RGBA", (w, h), buffer, "raw", "BGRA", 0, 1)
            return im.convert("RGB")
        except Exception:
            return None

    def find_color_button_center(
        self,
        hwnd: int,
        r_range: Tuple[int, int],
        g_range: Tuple[int, int],
        b_range: Tuple[int, int],
        search_region: Optional[Tuple[float, float, float, float]] = None,
        min_cluster_width: int = 15,
        min_cluster_height: int = 8,
    ) -> Optional[Tuple[int, int]]:
        """
        Locate the geometric center of a button defined by its signature color.
        search_region: (min_x_pct, min_y_pct, max_x_pct, max_y_pct)
        Returns absolute screen coordinates (screen_x, screen_y).
        """
        self.attach_to_desktop()
        rect = RECT()
        self.user32.GetWindowRect(ctypes.wintypes.HWND(hwnd), ctypes.byref(rect))
        w = max(10, rect.right - rect.left)
        h = max(10, rect.bottom - rect.top)

        im = self.capture_window_image(hwnd)
        if not im:
            return None

        min_x_pct, min_y_pct, max_x_pct, max_y_pct = search_region or (0.0, 0.0, 1.0, 1.0)
        x_start = max(0, int(w * min_x_pct))
        x_end = min(w, int(w * max_x_pct))
        y_start = max(0, int(h * min_y_pct))
        y_end = min(h, int(h * max_y_pct))

        pixels = []
        pix_access = im.load()

        for y in range(y_start, y_end, 3):
            for x in range(x_start, x_end, 4):
                r, g, b = pix_access[x, y]
                if (r_range[0] <= r <= r_range[1] and
                    g_range[0] <= g <= g_range[1] and
                    b_range[0] <= b <= b_range[1]):
                    pixels.append((x, y))

        if not pixels:
            return None

        # Cluster matching pixels by proximity to isolate individual buttons
        clusters: List[List[Tuple[int, int]]] = []
        for x, y in pixels:
            matched = False
            for c in clusters:
                if abs(x - c[0][0]) < 80 and abs(y - c[0][1]) < 35:
                    c.append((x, y))
                    matched = True
                    break
            if not matched:
                clusters.append([(x, y)])

        # Select the densest cluster matching minimum button dimensions
        valid_clusters = []
        for c in clusters:
            xs = [p[0] for p in c]
            ys = [p[1] for p in c]
            cw = max(xs) - min(xs)
            ch = max(ys) - min(ys)
            if cw >= min_cluster_width and ch >= min_cluster_height:
                valid_clusters.append((len(c), min(xs), max(xs), min(ys), max(ys)))

        if not valid_clusters:
            return None

        valid_clusters.sort(key=lambda item: item[0], reverse=True)
        _, min_px, max_px, min_py, max_py = valid_clusters[0]

        rel_cx = int((min_px + max_px) / 2)
        rel_cy = int((min_py + max_py) / 2)

        # Ensure correct screen mapping taking account of maximized window borders
        base_x = max(0, rect.left) if rect.left < 0 else rect.left
        base_y = max(0, rect.top) if rect.top < 0 else rect.top
        return (base_x + rel_cx, base_y + rel_cy)

    def find_facebook_primary_blue_button(
        self, hwnd: int, region: Optional[Tuple[float, float, float, float]] = None
    ) -> Optional[Tuple[int, int]]:
        """Find Facebook primary blue button ('Advertise', 'Publish', 'Turn on', 'Save')."""
        return self.find_color_button_center(
            hwnd=hwnd,
            r_range=(0, 65),
            g_range=(75, 175),
            b_range=(195, 255),
            search_region=region,
        )

    def find_facebook_secondary_grey_button(
        self, hwnd: int, region: Optional[Tuple[float, float, float, float]] = None
    ) -> Optional[Tuple[int, int]]:
        """Find Facebook secondary button ('Change', 'Use a post', 'Select media')."""
        return self.find_color_button_center(
            hwnd=hwnd,
            r_range=(215, 240),
            g_range=(220, 242),
            b_range=(225, 246),
            search_region=region,
            min_cluster_width=25,
            min_cluster_height=12,
        )

    def is_error_page_displayed(self, hwnd: int) -> bool:
        """
        Verify if Facebook is displaying an error or dead-end page
        e.g., 'This Page Isn't Available' or 'This content isn't available right now'.
        """
        im = self.capture_window_image(hwnd)
        if not im:
            return False

        w, h = im.size
        center_blue = self.find_facebook_primary_blue_button(
            hwnd=hwnd, region=(0.40, 0.65, 0.60, 0.85)
        )
        if center_blue:
            pix = im.load()
            bg_r, bg_g, bg_b = pix[int(w * 0.3), int(h * 0.5)]
            if bg_r > 230 and bg_g > 230 and bg_b > 230:
                return True
        return False

    def check_facebook_ad_restrictions(self, hwnd: int) -> Optional[str]:
        """
        Detect Facebook ad rejections or account advertising restrictions.
        e.g., 'We rejected your ad', 'Account Restricted', 'Advertising access restricted'.
        """
        im = self.capture_window_image(hwnd)
        if not im:
            return None

        w, h = im.size
        pix = im.load()
        red_pixels = []
        for y in range(0, min(h, 600), 3):
            for x in range(0, min(w, 800), 3):
                r, g, b = pix[x, y]
                if r > 200 and g < 75 and b < 75:
                    red_pixels.append((x, y))

        if len(red_pixels) >= 15:
            return "Meta Advertising Restriction Detected: 'We rejected your ad' or account policy flag."
        return None

    def is_ad_creation_page_active(self, hwnd: int) -> bool:
        """
        Verify if the Facebook Ad Creation / consolidated ad form is currently active on screen.
        Checks for the blue Publish button (bottom right) or Create Ad / Ad details indicators.
        """
        title = system_automation.get_window_title(hwnd).lower()
        if "create ad" in title or "ad details" in title:
            return True

        # Blue Publish button is centered around x=0.55..0.78, y=0.90..0.97
        publish_btn = self.find_facebook_primary_blue_button(
            hwnd=hwnd, region=(0.48, 0.82, 0.95, 0.99)
        )
        if publish_btn:
            return True

        # Fallback check for Goal 'Change' button or 'Audience' card
        change_btn = self.find_facebook_secondary_grey_button(
            hwnd=hwnd, region=(0.40, 0.55, 0.65, 0.75)
        )
        return change_btn is not None


smart_vision = SmartVisionLocator()
