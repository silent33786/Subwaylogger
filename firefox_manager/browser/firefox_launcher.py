"""
Native Firefox Process Launcher.
Launches native Windows Firefox instances directly using official command-line flags
(-profile and -no-remote). Manages process lifecycles and window focus.
"""

import os
import subprocess
import sys
import ctypes
from pathlib import Path
from typing import Optional, List

try:
    import winreg
except ImportError:  # Not Windows (or no winreg): registry lookup is unavailable.
    winreg = None  # type: ignore[assignment]

from firefox_manager.config.settings import settings


class FirefoxLauncher:
    """Manages direct execution of native local Firefox instances."""

    def __init__(self, executable_path: Optional[str] = None):
        # Do NOT raise here. Importing the app (or running --status /
        # --help / tests) must work on a machine without Firefox. The
        # missing-binary error is raised only in launch(), with a clear
        # message telling the user how to fix it.
        self.executable_path = executable_path or self.detect_firefox_binary()
        self._missing_binary_error: Optional[str] = None
        if not self.executable_path or not os.path.isfile(self.executable_path):
            self._missing_binary_error = (
                "Firefox executable could not be found. Install Firefox, or set "
                "the FIREFOX_BINARY environment variable to the full path of "
                f"firefox.exe. Checked path: {self.executable_path}"
            )
            self.executable_path = None

    @classmethod
    def detect_firefox_binary(cls) -> Optional[str]:
        """Detect Firefox installation from Registry and standard filesystem paths."""
        # Check settings first
        if settings.firefox_binary_path and os.path.isfile(settings.firefox_binary_path):
            return str(Path(settings.firefox_binary_path).resolve())

        # Check Windows App Paths Registry (Windows only)
        if winreg is not None:
            registry_keys = [
                (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths\firefox.exe"),
                (winreg.HKEY_CURRENT_USER, r"SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths\firefox.exe"),
                (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\App Paths\firefox.exe"),
            ]
            for hkey, subkey in registry_keys:
                try:
                    with winreg.OpenKey(hkey, subkey) as key:
                        val, _ = winreg.QueryValueEx(key, "")
                        if val and os.path.isfile(val):
                            return str(Path(val).resolve())
                except OSError:
                    pass

        # Standard file path fallbacks
        candidates = [
            r"C:\Program Files\Mozilla Firefox\firefox.exe",
            r"C:\Program Files (x86)\Mozilla Firefox\firefox.exe",
            os.path.expandvars(r"%LOCALAPPDATA%\Mozilla Firefox\firefox.exe"),
            os.path.expandvars(r"%ProgramFiles%\Mozilla Firefox\firefox.exe"),
            os.path.expandvars(r"%ProgramFiles(x86)%\Mozilla Firefox\firefox.exe"),
        ]
        for c in candidates:
            if c and os.path.isfile(c):
                return str(Path(c).resolve())

        return None

    def launch(
        self,
        profile_path: Path,
        initial_url: Optional[str] = None,
        extra_args: Optional[List[str]] = None,
    ) -> subprocess.Popen:
        """
        Launch Firefox natively bound to the specified isolated profile directory.
        Uses official '-profile' and '-no-remote' flags to guarantee profile isolation.
        """
        if not self.executable_path:
            raise FileNotFoundError(
                self._missing_binary_error
                or "Firefox executable could not be found. Install Firefox or set FIREFOX_BINARY."
            )
        resolved_profile = Path(profile_path).resolve()
        if not resolved_profile.is_dir():
            raise FileNotFoundError(f"Profile directory does not exist: {resolved_profile}")

        cmd = [
            self.executable_path,
            "-profile",
            str(resolved_profile),
            "-no-remote",
        ]

        if extra_args:
            cmd.extend(extra_args)

        if initial_url:
            cmd.append(initial_url)

        # On Windows, start as a detached process or in its own group to prevent parent signal cascading
        creationflags = 0
        if sys.platform == "win32":
            creationflags = subprocess.CREATE_NEW_PROCESS_GROUP

        process = subprocess.Popen(
            cmd,
            creationflags=creationflags,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            stdin=subprocess.DEVNULL,
        )

        return process

    def bring_window_to_front(self, pid: int) -> bool:
        """
        Bring the Firefox window for the specified PID to the foreground on Windows.
        Essential for human-in-the-loop CAPTCHA or security verification.
        """
        if sys.platform != "win32":
            return False

        user32 = ctypes.windll.user32
        target_hwnd = None

        # Callback for EnumWindows
        WNDENUMPROC = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_void_p, ctypes.c_void_p)

        def enum_windows_callback(hwnd, extra):
            nonlocal target_hwnd
            window_pid = ctypes.c_ulong()
            user32.GetWindowThreadProcessId(hwnd, ctypes.byref(window_pid))
            if window_pid.value == pid and user32.IsWindowVisible(hwnd):
                length = user32.GetWindowTextLengthW(hwnd)
                buff = ctypes.create_unicode_buffer(length + 1)
                user32.GetWindowTextW(hwnd, buff, length + 1)
                title = buff.value
                if title:  # Has a visible title
                    target_hwnd = hwnd
                    return False  # Stop enumeration
            return True

        cb = WNDENUMPROC(enum_windows_callback)
        user32.EnumWindows(cb, 0)

        if target_hwnd:
            SW_RESTORE = 9
            user32.ShowWindow(target_hwnd, SW_RESTORE)
            user32.SetForegroundWindow(target_hwnd)
            return True

        return False
