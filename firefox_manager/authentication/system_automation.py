"""
System-Level OS Native Browser Automation Engine.
Pure native OS execution:
- ZERO browser tampering, NO WebDriver, NO Selenium, NO Playwright, NO CDP/Marionette.
- Uses 64-bit pure Win32 Clipboard API (OpenClipboard, EmptyClipboard, SetClipboardData)
  which works 100% reliably in background threads without Qt OLE/COM restrictions.
- Accurately focuses Firefox and clicks into the Facebook Email and Password fields.
- Uses Windows OS Clipboard Paste (Ctrl+V) for 100% reliable character transmission without dropped keystrokes.
- Immediately wipes clipboard memory after typing for credential safety.
"""

import sys
import time
import ctypes
from typing import Optional, Callable, Dict, Any, List
from datetime import datetime, timezone
import psutil

from firefox_manager.config.settings import settings
from firefox_manager.database.database import db
from firefox_manager.database.models import AccountRecord, AccountStatus, AuditSeverity
from firefox_manager.core.profile_manager import profile_manager
from firefox_manager.core.process_manager import process_manager
from firefox_manager.browser.profile_storage import profile_storage
from firefox_manager.security.credential_manager import credential_manager
from firefox_manager.security.audit_logger import audit_logger


# Virtual Key Codes
VK_ESCAPE = 0x1B
VK_TAB = 0x09
VK_RETURN = 0x0D
VK_BACK = 0x08
VK_CONTROL = 0x11
VK_MENU = 0x12
VK_A = 0x41
VK_V = 0x56
KEYEVENTF_KEYUP = 0x0002
KEYEVENTF_UNICODE = 0x0004
MOUSEEVENTF_LEFTDOWN = 0x0002
MOUSEEVENTF_LEFTUP = 0x0004


class RECT(ctypes.Structure):
    _fields_ = [
        ("left", ctypes.c_long),
        ("top", ctypes.c_long),
        ("right", ctypes.c_long),
        ("bottom", ctypes.c_long),
    ]


class SystemLevelAutomation:
    """Enterprise OS-level automation for native, untouched Firefox profiles."""

    def __init__(self):
        self.user32 = ctypes.windll.user32 if sys.platform == "win32" else None
        self.kernel32 = ctypes.windll.kernel32 if sys.platform == "win32" else None

        if sys.platform == "win32":
            try:
                ctypes.windll.shcore.SetProcessDpiAwareness(2)
            except Exception:
                try:
                    ctypes.windll.user32.SetProcessDPIAware()
                except Exception:
                    pass

        if self.user32 and self.kernel32:
            # Configure Win32 64-bit function signatures
            self.kernel32.GlobalAlloc.argtypes = [ctypes.c_uint, ctypes.c_size_t]
            self.kernel32.GlobalAlloc.restype = ctypes.c_void_p
            self.kernel32.GlobalLock.argtypes = [ctypes.c_void_p]
            self.kernel32.GlobalLock.restype = ctypes.c_void_p
            self.kernel32.GlobalUnlock.argtypes = [ctypes.c_void_p]
            self.kernel32.GlobalUnlock.restype = ctypes.c_bool

            self.user32.OpenClipboard.argtypes = [ctypes.c_void_p]
            self.user32.OpenClipboard.restype = ctypes.c_bool
            self.user32.CloseClipboard.argtypes = []
            self.user32.CloseClipboard.restype = ctypes.c_bool
            self.user32.EmptyClipboard.argtypes = []
            self.user32.EmptyClipboard.restype = ctypes.c_bool
            self.user32.SetClipboardData.argtypes = [ctypes.c_uint, ctypes.c_void_p]
            self.user32.SetClipboardData.restype = ctypes.c_void_p
            self.user32.GetClipboardData.argtypes = [ctypes.c_uint]
            self.user32.GetClipboardData.restype = ctypes.c_void_p

    def send_key(self, vk: int) -> None:
        """Send virtual key press and release."""
        if not self.user32:
            return
        self.user32.keybd_event(vk, 0, 0, 0)
        time.sleep(0.06)
        self.user32.keybd_event(vk, 0, KEYEVENTF_KEYUP, 0)
        time.sleep(0.08)

    def send_ctrl_v(self) -> None:
        """Simulate native Windows Ctrl+V paste."""
        if not self.user32:
            return
        self.user32.keybd_event(VK_CONTROL, 0, 0, 0)
        time.sleep(0.06)
        self.user32.keybd_event(VK_V, 0, 0, 0)
        time.sleep(0.06)
        self.user32.keybd_event(VK_V, 0, KEYEVENTF_KEYUP, 0)
        self.user32.keybd_event(VK_CONTROL, 0, KEYEVENTF_KEYUP, 0)
        time.sleep(0.12)

    def send_ctrl_a_backspace(self) -> None:
        """Clear existing text in active input field."""
        if not self.user32:
            return
        self.user32.keybd_event(VK_CONTROL, 0, 0, 0)
        time.sleep(0.05)
        self.user32.keybd_event(VK_A, 0, 0, 0)
        time.sleep(0.05)
        self.user32.keybd_event(VK_A, 0, KEYEVENTF_KEYUP, 0)
        self.user32.keybd_event(VK_CONTROL, 0, KEYEVENTF_KEYUP, 0)
        time.sleep(0.08)
        self.send_key(VK_BACK)

    def safe_clear_focused_input(self) -> None:
        """
        Safely clears an input field without risking selecting the whole webpage.
        Sends End -> Shift+Home -> Backspace -> Backspaces sequence.
        """
        if not self.user32:
            return
        # Send End
        self.send_key(0x23)  # VK_END
        time.sleep(0.05)
        # Shift + Home selects line inside input
        self.user32.keybd_event(0x10, 0, 0, 0)  # VK_SHIFT
        self.user32.keybd_event(0x24, 0, 0, 0)  # VK_HOME
        time.sleep(0.06)
        self.user32.keybd_event(0x24, 0, KEYEVENTF_KEYUP, 0)
        self.user32.keybd_event(0x10, 0, KEYEVENTF_KEYUP, 0)
        time.sleep(0.06)
        self.send_key(VK_BACK)
        time.sleep(0.05)
        # Multi-backspace to ensure blank
        for _ in range(25):
            self.user32.keybd_event(VK_BACK, 0, 0, 0)
            self.user32.keybd_event(VK_BACK, 0, KEYEVENTF_KEYUP, 0)
            time.sleep(0.02)

    def set_clipboard(self, text: str) -> bool:
        """
        Set clipboard text using pure 64-bit Win32 API.
        Works across all threads without Qt OLE/COM restrictions.
        """
        if not self.user32 or not self.kernel32:
            return False

        for attempt in range(10):
            if self.user32.OpenClipboard(None):
                self.user32.EmptyClipboard()
                if text:
                    text_bytes = text.encode("utf-16le") + b"\x00\x00"
                    h_mem = self.kernel32.GlobalAlloc(0x0002, len(text_bytes))  # GMEM_MOVEABLE
                    if h_mem:
                        p_mem = self.kernel32.GlobalLock(h_mem)
                        if p_mem:
                            ctypes.memmove(p_mem, text_bytes, len(text_bytes))
                            self.kernel32.GlobalUnlock(h_mem)
                            self.user32.SetClipboardData(13, h_mem)  # CF_UNICODETEXT
                self.user32.CloseClipboard()
                return True
            time.sleep(0.05)
        return False

    def clear_clipboard(self) -> None:
        """Wipe clipboard memory for credential security."""
        self.set_clipboard("")

    def paste_into_focused_input(self, text: str) -> None:
        """Copy exact text to clipboard, send Ctrl+V, and immediately erase clipboard.

        The old version ignored set_clipboard()'s return value, so if the
        clipboard was busy it still sent Ctrl+V and pasted whatever stale
        content (possibly the previous credential) was there. Now a
        failed clipboard set raises instead of pasting the wrong thing.
        """
        if not self.set_clipboard(text):
            raise RuntimeError("Could not set the clipboard - refusing to paste stale content.")
        time.sleep(0.08)
        self.send_ctrl_v()
        time.sleep(0.08)
        self.clear_clipboard()

    def mouse_click(self, x: int, y: int) -> None:
        """Simulate real hardware left-click at screen coordinates (x, y)."""
        if not self.user32:
            return
        self.user32.SetCursorPos(x, y)
        time.sleep(0.1)
        self.user32.mouse_event(MOUSEEVENTF_LEFTDOWN, 0, 0, 0, 0)
        time.sleep(0.08)
        self.user32.mouse_event(MOUSEEVENTF_LEFTUP, 0, 0, 0, 0)
        time.sleep(0.2)

    def mouse_double_click(self, x: int, y: int) -> None:
        """Simulate real hardware double-click at screen coordinates (x, y) to focus inputs."""
        if not self.user32:
            return
        self.user32.SetCursorPos(x, y)
        time.sleep(0.1)
        self.user32.mouse_event(MOUSEEVENTF_LEFTDOWN, 0, 0, 0, 0)
        time.sleep(0.05)
        self.user32.mouse_event(MOUSEEVENTF_LEFTUP, 0, 0, 0, 0)
        time.sleep(0.08)
        self.user32.mouse_event(MOUSEEVENTF_LEFTDOWN, 0, 0, 0, 0)
        time.sleep(0.05)
        self.user32.mouse_event(MOUSEEVENTF_LEFTUP, 0, 0, 0, 0)
        time.sleep(0.25)

    def find_firefox_window(self, target_pid: Optional[int] = None) -> Optional[int]:
        """
        Locate top-level Firefox window across all processes and child threads.
        Matches process name 'firefox.exe' and title containing 'Facebook' or 'Mozilla Firefox'.
        """
        if not self.user32:
            return None

        candidates = []
        WNDENUMPROC = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_void_p, ctypes.c_void_p)

        def enum_cb(hwnd, extra):
            if self.user32.IsWindowVisible(hwnd):
                pid = ctypes.c_ulong()
                self.user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
                try:
                    proc = psutil.Process(pid.value)
                    if "firefox" in proc.name().lower():
                        length = self.user32.GetWindowTextLengthW(hwnd)
                        buff = ctypes.create_unicode_buffer(length + 1)
                        self.user32.GetWindowTextW(hwnd, buff, length + 1)
                        title = buff.value
                        if title:
                            candidates.append((hwnd, pid.value, title))
                except Exception:
                    pass
            return True

        self.user32.EnumWindows(WNDENUMPROC(enum_cb), 0)

        # Fallback to desktop enumeration if EnumWindows returned no candidates
        if not candidates:
            try:
                import win32service, win32gui, win32con
                desk = win32service.OpenInputDesktop(0, False, win32con.GENERIC_ALL)
                def desk_cb(h, _):
                    if win32gui.IsWindowVisible(h):
                        t = win32gui.GetWindowText(h)
                        if t and ("facebook" in t.lower() or "firefox" in t.lower() or "mozilla" in t.lower()):
                            candidates.append((h, 0, t))
                win32gui.EnumDesktopWindows(desk, desk_cb, None)
            except Exception:
                pass

        if not candidates:
            return None

        # Prioritize matching target PID
        if target_pid:
            for hwnd, pid, title in candidates:
                if pid == target_pid:
                    return hwnd

        # Prioritize title containing 'Facebook'
        for hwnd, pid, title in candidates:
            if "facebook" in title.lower():
                return hwnd

        # Default to first Firefox window
        return candidates[0][0]

    def force_focus_window(self, hwnd: int) -> bool:
        """
        Force window to foreground and maximize using Windows Win32 API.
        Bypasses Windows Foreground Lock Timeout via AttachThreadInput & SetWindowPos.
        """
        if not self.user32 or not self.kernel32:
            return False

        # 1. Maximize window using WM_SYSCOMMAND SC_MAXIMIZE and ShowWindow
        WM_SYSCOMMAND = 0x0112
        SC_MAXIMIZE = 0xF030
        SW_MAXIMIZE = 3
        self.user32.PostMessageW(hwnd, WM_SYSCOMMAND, SC_MAXIMIZE, 0)
        self.user32.ShowWindow(hwnd, SW_MAXIMIZE)

        # 2. Bring to topmost temporarily, then restore normal z-order
        HWND_TOPMOST = -1
        HWND_NOTOPMOST = -2
        SWP_NOMOVE = 0x0002
        SWP_NOSIZE = 0x0001
        self.user32.SetWindowPos(hwnd, HWND_TOPMOST, 0, 0, 0, 0, SWP_NOMOVE | SWP_NOSIZE)
        self.user32.SetWindowPos(hwnd, HWND_NOTOPMOST, 0, 0, 0, 0, SWP_NOMOVE | SWP_NOSIZE)

        # 3. Attach input thread to bypass foreground lock
        cur_thread = self.kernel32.GetCurrentThreadId()
        win_thread = self.user32.GetWindowThreadProcessId(hwnd, None)
        self.user32.AttachThreadInput(cur_thread, win_thread, True)

        self.user32.SetForegroundWindow(hwnd)
        self.user32.BringWindowToTop(hwnd)
        self.user32.SetFocus(hwnd)

        self.user32.AttachThreadInput(cur_thread, win_thread, False)
        time.sleep(0.6)
        return True

    def get_window_title(self, hwnd: int) -> str:
        """Fetch current text of the window title bar."""
        try:
            import win32service, win32gui, win32con
            desk = win32service.OpenInputDesktop(0, False, win32con.GENERIC_ALL)
            desk.SetThreadDesktop()
            title = win32gui.GetWindowText(hwnd)
            if title:
                return title
        except Exception:
            pass
        if not self.user32:
            return ""
        try:
            length = self.user32.GetWindowTextLengthW(hwnd)
            buff = ctypes.create_unicode_buffer(length + 1)
            self.user32.GetWindowTextW(hwnd, buff, length + 1)
            return buff.value or ""
        except Exception:
            return ""

    def handle_open_file_dialog(self, file_path: str, timeout: float = 6.0) -> bool:
        """
        Detects standard Windows Open File Dialog (#32770) spawned by Firefox,
        pastes the absolute file path, and submits it.
        """
        from pathlib import Path
        p = Path(file_path)
        if not self.user32 or not p.exists():
            return False

        start_t = time.time()
        while time.time() - start_t < timeout:
            dialog_hwnd = self.user32.FindWindowW("#32770", None)
            if dialog_hwnd and self.user32.IsWindowVisible(dialog_hwnd):
                self.force_focus_window(dialog_hwnd)
                time.sleep(0.3)
                self.paste_into_focused_input(str(p.resolve()))
                time.sleep(0.3)
                self.send_key(VK_RETURN)
                time.sleep(1.0)
                return True
            time.sleep(0.3)
        return False

    def check_facebook_session_status(self, directory_name: str) -> Dict[str, Any]:
        """
        Inspect Firefox's persistent cookies.sqlite in read-only mode.
        Returns whether the account has reached authenticated state.

        Limitation, documented honestly: logged-in is decided ONLY by
        the presence of Facebook's `c_user` session cookie. There is no
        cookie literally named 'checkpoint' that reliably signals a
        security checkpoint (the old code queried for one, so it almost
        never detected a checkpoint from cookies). Checkpoint detection
        must come from the window title / page state, checked by the
        caller - see run_facebook_login_system_level().
        """
        profile_path = profile_storage.get_profile_path(directory_name)
        cookies_db = profile_path / "cookies.sqlite"
        if not cookies_db.exists():
            return {"logged_in": False, "c_user": None, "has_checkpoint": False}

        try:
            import sqlite3
            uri_path = f"file:{cookies_db.resolve().as_posix()}?mode=ro&immutable=1"
            conn = sqlite3.connect(uri_path, uri=True, timeout=2.0)
            cur = conn.cursor()
            cur.execute(
                "SELECT name, value FROM moz_cookies WHERE host LIKE ? AND name = 'c_user'",
                ("%facebook.com%",),
            )
            rows = dict(cur.fetchall())
            conn.close()

            c_user = rows.get("c_user")
            return {
                "logged_in": bool(c_user),
                "c_user": c_user,
                # Always False from cookies alone; callers detect a
                # checkpoint from the window title instead.
                "has_checkpoint": False,
            }
        except Exception:
            return {"logged_in": False, "c_user": None, "has_checkpoint": False}

    def run_facebook_login_system_level(
        self,
        profile_id: str,
        username_or_uid: str,
        password: str,
        page_load_delay: float = 6.0,
        status_callback: Optional[Callable[[str], None]] = None,
        save_to_vault: bool = True,
    ) -> Dict[str, Any]:
        """
        Execute system-level Facebook sign-in:
        1. Launches pure native Firefox.
        2. Waits for page to render.
        3. Restores and activates Firefox window.
        4. Clicks directly into the Email field and pastes ONLY the UID (Ctrl+V).
        5. Clicks directly into the Password field and pastes ONLY the Password (Ctrl+V).
        6. Immediately wipes clipboard.
        7. Submits with Enter.
        """
        def log_step(msg: str):
            if status_callback:
                status_callback(msg)
            audit_logger.log(
                agent_name="SystemAutomation",
                action="SYSTEM_AUTO_STEP",
                target=username_or_uid,
                details=msg,
            )

        log_step("Validating profile...")
        profile = db.get_profile(profile_id)
        if not profile:
            raise ValueError(f"Profile '{profile_id}' not found.")

        # 1. Launch pure native Firefox to Facebook
        fb_url = "https://www.facebook.com/"
        log_step(f"Launching untouched native Firefox to {fb_url}...")

        if process_manager.is_running(profile.id):
            pid = process_manager.get_pid(profile.id)
            process_manager.bring_to_front(profile.id)
        else:
            pid = profile_manager.launch_profile(profile.id, initial_url=fb_url)

        if not pid:
            raise RuntimeError("Failed to launch native Firefox process.")

        # 2. Wait for page load
        log_step(f"Waiting {page_load_delay}s for Facebook page to render in Firefox...")
        time.sleep(page_load_delay)

        # 3. Locate and focus the exact Firefox window
        log_step("Detecting Firefox window on Windows OS...")
        hwnd = self.find_firefox_window(target_pid=pid)
        if not hwnd:
            time.sleep(2.0)
            hwnd = self.find_firefox_window()

        if not hwnd:
            raise RuntimeError("Could not find visible Firefox window on the system.")

        # 4. Focus the Firefox window once (this block was duplicated).
        log_step(f"Bringing Firefox window (HWND: {hwnd}) to foreground...")
        self.force_focus_window(hwnd)
        time.sleep(0.8)

        # 5. Dismiss any initial browser autocomplete or import prompts
        self.send_key(VK_ESCAPE)
        time.sleep(0.3)

        # 6. Type UID into autofocused Facebook Email field
        log_step(f"Pasting ONLY Facebook UID into Email field: {username_or_uid}...")
        self.send_ctrl_a_backspace()
        self.paste_into_focused_input(username_or_uid)
        time.sleep(0.5)

        # 7. Tab directly into Password field (native HTML tab order: #email -> #pass)
        log_step("Sending Tab key to switch focus directly to Password field...")
        self.send_key(VK_TAB)
        time.sleep(0.5)

        # 8. Type Password into Password field
        log_step("Pasting ONLY Password into Password field...")
        self.send_ctrl_a_backspace()
        self.paste_into_focused_input(password)
        time.sleep(0.5)

        # 9. Submit login form with Enter
        log_step("Submitting login form (Enter)...")
        self.send_key(VK_RETURN)
        time.sleep(1.2)

        # 10. Real-time Monitoring: Watch until Facebook Home Page is
        # reached or a CAPTCHA / checkpoint appears. NOTE: nothing is
        # saved to the DB or vault here. The old code marked the account
        # ACTIVE and stored the password BEFORE knowing whether the
        # login had worked. Saving now happens only after
        # home_page_reached is True (step 11 below).
        log_step("🔍 Monitoring post-login state: Waiting for Facebook Home Page to load...")
        monitor_start = time.time()
        max_wait_seconds = 45.0
        home_page_reached = False
        challenge_notified = False
        verification_timed_out = False

        while (time.time() - monitor_start) < max_wait_seconds:
            time.sleep(1.5)

            status = self.check_facebook_session_status(profile.directory_name)
            current_title = self.get_window_title(hwnd).lower()

            # A. Check for CAPTCHA / 2FA / Security Checkpoint. The
            # cookie check cannot detect a checkpoint (see
            # check_facebook_session_status), so the window title is
            # the signal here.
            challenge_keywords = [
                "security check", "checkpoint", "two-factor", "confirm your identity",
                "verification", "enter code", "captcha", "security code", "help us confirm"
            ]
            is_challenge = any(kw in current_title for kw in challenge_keywords)

            if is_challenge and not challenge_notified:
                challenge_notified = True
                log_step("⚠️ CAPTCHA / Security Challenge detected!")
                log_step("👉 Human-in-the-Loop Protocol: Bringing Firefox to front. Please solve the challenge in the browser window.")
                self.force_focus_window(hwnd)

                # Human-in-the-loop: request verification AND WAIT for
                # the user to resolve it. The old code fired the request
                # and carried on looping, then returned success anyway.
                # No CAPTCHA / 2FA code is ever entered by automation.
                verification_request = None
                try:
                    from firefox_manager.core.orchestrator import orchestrator
                    verification_request = orchestrator.verification_handler.request_human_verification(
                        profile_id=profile.id,
                        challenge_type="Facebook Security Checkpoint / CAPTCHA",
                        details="Facebook requested security verification. Please solve it in the open Firefox window.",
                    )
                except Exception:
                    verification_request = None

                if verification_request is not None:
                    log_step("⏸️ Paused: waiting up to 300s for you to complete the verification in Firefox...")
                    resolved = verification_request.wait_for_resolution(timeout=300)
                    if not resolved:
                        verification_timed_out = True
                        log_step("⏰ Verification was not completed within 300s.")
                        break
                    if not verification_request.success:
                        log_step("Verification was marked as failed / cancelled by the user.")
                        break
                    log_step("✓ Verification resolved by the user. Re-checking login state...")
                    challenge_notified = False  # re-arm: a second challenge is possible
                    monitor_start = time.time()  # fresh 45s window after the user finishes
                    continue

            # B. Check for Facebook Home Page Success
            # Case 1: Persistent c_user cookie confirmed
            if status.get("logged_in") and status.get("c_user"):
                home_page_reached = True
                log_step("🎉 Facebook Home Page Reached! Authenticated session verified.")
                log_step("✓ Automation Completed Successfully! Session is persistent.")
                break

            # Case 2: Title indicates Home Page and not login or challenge.
            # Title alone is weak evidence, so it only counts when the
            # c_user cookie is also present (checked above) OR the title
            # is exactly a home-page title with no login wording. The
            # old code accepted any "facebook" title, including the
            # login page itself, as success.
            if (
                current_title.strip() == "facebook"
                and not is_challenge
                and status.get("logged_in")
            ):
                home_page_reached = True
                log_step("🎉 Facebook Home Page Reached! Automation Completed Successfully.")
                break

        # 11. Save account record in DB and OS vault - ONLY after the
        # login has actually been verified.
        if home_page_reached:
            log_step("Saving account record in database and secure vault...")
            now_iso = datetime.now(timezone.utc).isoformat()
            accounts = db.list_accounts()
            fb_account = None

            for a in accounts:
                if a.service_name.lower() == "facebook" and a.username.lower() == username_or_uid.lower():
                    fb_account = a
                    break

            if fb_account:
                fb_account.profile_id = profile_id
                fb_account.status = AccountStatus.ACTIVE
                fb_account.last_login_at = now_iso
                db.update_account(fb_account)
            else:
                fb_account = AccountRecord(
                    service_name="Facebook",
                    username=username_or_uid,
                    profile_id=profile_id,
                    status=AccountStatus.ACTIVE,
                    last_login_at=now_iso,
                    notes="Automated system-level sign-in",
                )
                db.create_account(fb_account)

            if save_to_vault and password:
                credential_manager.store_credential(
                    service_name="Facebook",
                    username=username_or_uid,
                    secret=password,
                )
        else:
            # Never mark ACTIVE / store the password for a login that
            # did not verify. Record the attempt as needing login so
            # the dashboard does not show a false "connected" account.
            try:
                accounts = db.list_accounts()
                for a in accounts:
                    if a.service_name.lower() == "facebook" and a.username.lower() == username_or_uid.lower():
                        db.update_account_status(a.id, AccountStatus.REQUIRES_LOGIN)
                        break
            except Exception:
                pass

        if not home_page_reached:
            if verification_timed_out:
                message = "Verification not completed - login not verified."
            elif challenge_notified:
                message = "Security challenge is active - login not verified. Complete it in Firefox and retry."
            else:
                message = "Login not verified - home page was not reached."
            log_step(f"⚠️ {message}")
            return {
                "success": False,
                "pid": pid,
                "home_page_reached": False,
                "message": message,
            }

        return {
            "success": True,
            "pid": pid,
            "home_page_reached": True,
            "message": "Facebook Home Page reached & session verified.",
        }

    def run_batch_facebook_automation(
        self,
        account_lines: List[str],
        page_load_delay: float = 6.0,
        delay_between_accounts: float = 4.0,
        status_callback: Optional[Callable[[str], None]] = None,
        progress_callback: Optional[Callable[[int, int], None]] = None,
    ) -> Dict[str, Any]:
        """
        Automatic Bulk Profile Creation & OS-Level Login Engine:
        For each account in list:
        1. Automatically creates a dedicated, isolated Firefox profile.
        2. Launches native Firefox directly to Facebook.
        3. Clicks into email box, dismisses popups, pastes UID + Password separately.
        4. Saves account in SQLite and encrypts password in Windows vault.
        5. Automatically continues to the next account!
        """
        def log_step(msg: str):
            if status_callback:
                status_callback(msg)
            audit_logger.log(
                agent_name="BatchAutomation",
                action="BATCH_STEP",
                details=msg,
            )

        # Parse each line on its FIRST separator only. The old code tried
        # separators in order (":", "|", tab, ",") and split on whichever
        # appeared first in the line, so a password containing ":" was
        # split at the wrong place. Splitting on the first separator
        # only is still ambiguous if a password contains the separator,
        # so the file format is: first separator separates user/pass.
        parsed_accounts = []
        skipped_lines: List[Dict[str, Any]] = []
        for line_no, raw_line in enumerate(account_lines, start=1):
            line = raw_line.strip()
            if not line or line.startswith("#"):
                continue

            user_part, pass_part = None, None
            for sep in [":", "|", "\t", ","]:
                if sep in line:
                    parts = line.split(sep, 1)
                    user_part = parts[0].strip()
                    pass_part = parts[1].strip()
                    break

            # Was: lines with an empty user or password were silently
            # dropped. Now they are reported as skipped entries.
            if not user_part or not pass_part:
                skipped_lines.append(
                    {"line": line_no, "success": False,
                     "error": "Skipped: empty username or password on this line."}
                )
                continue
            parsed_accounts.append((user_part, pass_part))

        total = len(parsed_accounts)
        if total == 0:
            raise ValueError(
                "No valid accounts found. Please enter accounts in format UID:Password (one per line)."
            )

        log_step(f"🚀 Loaded {total} account(s) for automatic profile creation and login.")
        if skipped_lines:
            log_step(f"⚠️ {len(skipped_lines)} line(s) skipped (empty username or password).")
        results: List[Dict[str, Any]] = list(skipped_lines)

        previous_profile_id: Optional[str] = None
        for idx, (username_or_uid, password) in enumerate(parsed_accounts, start=1):
            if progress_callback:
                progress_callback(idx, total)

            log_step("=" * 55)
            log_step(f"[{idx}/{total}] Processing Account: {username_or_uid}")

            # Stop the previous account's Firefox before starting the
            # next one. The old code never stopped it, so profiles
            # piled up until the max-concurrent limit was hit and
            # later accounts failed. Also enforce the limit up front.
            if previous_profile_id and process_manager.is_running(previous_profile_id):
                log_step(f"Stopping previous profile's Firefox before starting the next account...")
                try:
                    process_manager.stop_profile_process(previous_profile_id)
                except Exception as e:
                    log_step(f"⚠️ Could not stop previous Firefox: {e}")
            if process_manager.get_active_count() >= settings.max_concurrent_profiles:
                results.append({"user": username_or_uid, "success": False,
                                "error": f"Maximum concurrent profiles ({settings.max_concurrent_profiles}) reached."})
                log_step(f"❌ Skipped account {idx}/{total}: concurrent-profile limit reached.")
                continue

            # 1. Automatic Profile Resolution or Creation
            clean_name = f"FB_{username_or_uid.replace('@', '_').replace('.', '_')}"
            existing_profile = db.get_profile_by_name(clean_name)

            if not existing_profile:
                log_step(f"Creating dedicated Firefox profile '{clean_name}' automatically...")
                try:
                    profile = profile_manager.create_profile(
                        name=clean_name,
                        notes=f"Auto-generated for FB UID: {username_or_uid}",
                        tags="facebook, auto",
                    )
                    log_step(f"✓ Created profile '{clean_name}' (ID: {profile.id[:8]}...)")
                except Exception as e:
                    log_step(f"❌ Failed to create profile: {e}")
                    results.append({"user": username_or_uid, "success": False, "error": str(e)})
                    continue
            else:
                profile = existing_profile
                log_step(f"Using existing dedicated profile '{clean_name}'")

            # 2. Run OS-level login. Was: every non-exception return was
            # recorded as success, even when the login had not verified.
            # Now the per-account result follows the login result.
            previous_profile_id = profile.id
            try:
                res = self.run_facebook_login_system_level(
                    profile_id=profile.id,
                    username_or_uid=username_or_uid,
                    password=password,
                    page_load_delay=page_load_delay,
                    status_callback=status_callback,
                    save_to_vault=True,
                )
                ok = bool(res.get("success"))
                results.append({"user": username_or_uid, "success": ok, "profile": clean_name,
                                **({} if ok else {"error": res.get("message", "Login not verified.")})})
                if ok:
                    log_step(f"✓ Completed account {idx}/{total} ({username_or_uid})")
                else:
                    log_step(f"❌ Login not verified for account {idx}/{total} ({username_or_uid}): {res.get('message')}")
            except Exception as e:
                log_step(f"❌ Error during login for {username_or_uid}: {e}")
                results.append({"user": username_or_uid, "success": False, "error": str(e)})

            # Pause before starting next account
            if idx < total:
                log_step(f"Pausing {delay_between_accounts}s before starting next account...")
                time.sleep(delay_between_accounts)

        log_step("=" * 55)
        log_step(f"🎉 Batch automation completed! {len([r for r in results if r['success']])}/{total} succeeded.")
        return {
            "total": total,
            "succeeded": len([r for r in results if r["success"]]),
            "results": results,
        }


# Global instance
system_automation = SystemLevelAutomation()
