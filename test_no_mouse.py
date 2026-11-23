"""Safe manual smoke test for the no-mouse Facebook login sequence.

SECURITY: this file must NEVER contain a real UID, email, or password.
Credentials come only from environment variables or a getpass() prompt,
are never printed, never logged, and are cleared from memory when done.

Usage (Windows, from the project root):
    set FB_UID=your-uid-or-email
    python test_no_mouse.py
    # If FB_PASSWORD is not set, you will be prompted securely with getpass.

Set FB_TEST_PROFILE to use a different throwaway profile name.
This test is a manual smoke test only - it launches real Firefox and
is skipped by the automated pytest suite.
"""
import getpass
import os
import subprocess
import sys
import time

from firefox_manager.config.settings import settings
from firefox_manager.authentication.system_automation import system_automation


def _get_credential() -> tuple[str, str]:
    uid = os.environ.get("FB_UID", "").strip()
    if not uid:
        uid = input("Facebook UID / email: ").strip()
    password = os.environ.get("FB_PASSWORD", "")
    if not password:
        password = getpass.getpass("Facebook password (hidden, not echoed): ")
    assert uid, "FB_UID is required (env FB_UID or typed at the prompt)"
    assert password, "FB_PASSWORD is required (env FB_PASSWORD or getpass prompt)"
    return uid, password


def main() -> int:
    if sys.platform != "win32":
        print("This smoke test requires Windows (Win32 clipboard / input APIs).")
        return 2
    firefox_binary = settings.require_firefox_binary()
    uid, password = _get_credential()
    try:
        profile_dir = settings.profiles_dir / os.environ.get("FB_TEST_PROFILE", "test_no_mouse")
        profile_dir.mkdir(parents=True, exist_ok=True)
        proc = subprocess.Popen(
            [firefox_binary, "-profile", str(profile_dir), "-no-remote",
             "https://www.facebook.com/"]
        )
        try:
            time.sleep(8)
            hwnd = system_automation.find_firefox_window(target_pid=proc.pid)
            print("Found hwnd:", hwnd)
            assert hwnd, "Could not find the Firefox window for the test profile"
            system_automation.force_focus_window(hwnd)
            time.sleep(1.0)
            system_automation.send_key(0x1B)  # Escape: dismiss any initial popup
            time.sleep(0.3)
            print("Pasting UID into autofocused Email field...")
            system_automation.paste_into_focused_input(uid)
            time.sleep(0.5)
            print("Sending TAB to move to Password field...")
            system_automation.send_key(0x09)
            time.sleep(0.5)
            print("Pasting password into Password field...")
            system_automation.paste_into_focused_input(password)
            time.sleep(1.0)
            print("Sending Enter...")
            system_automation.send_key(0x0D)
            time.sleep(4.0)
            print("Finished sequence! Check the Firefox window: if a CAPTCHA / "
                  "2FA challenge appeared, solve it yourself in the browser.")
            return 0
        finally:
            # Always clean up the Firefox process we started, even on failure.
            if sys.platform == "win32":
                subprocess.run(
                    ["taskkill", "/F", "/T", "/PID", str(proc.pid)],
                    capture_output=True, timeout=10,
                )
            else:
                proc.terminate()
    finally:
        # Never leave the password in memory longer than needed.
        password = ""  # noqa: F841 - deliberate clearing


if __name__ == "__main__":
    raise SystemExit(main())
