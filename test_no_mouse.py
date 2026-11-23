import time
import subprocess
import ctypes
from firefox_manager.config.settings import settings
from firefox_manager.authentication.system_automation import system_automation

ff = settings.firefox_binary_path
profile_dir = settings.profiles_dir / "test_no_mouse"
profile_dir.mkdir(parents=True, exist_ok=True)

proc = subprocess.Popen([ff, "-profile", str(profile_dir), "-no-remote", "https://www.facebook.com/"])
time.sleep(8)

try:
    hwnd = system_automation.find_firefox_window(target_pid=proc.pid)
    print("Found hwnd:", hwnd)
    if hwnd:
        system_automation.force_focus_window(hwnd)
        time.sleep(1.0)

        # Send Escape to dismiss any initial popup without clicking
        system_automation.send_key(0x1B)
        time.sleep(0.3)

        # Paste UID into already-autofocused Email input
        print("Pasting UID into autofocused Email field...")
        system_automation.paste_into_focused_input("61562168636773")
        time.sleep(0.5)

        # Send Tab to move to Password field
        print("Sending TAB to move to Password field...")
        system_automation.send_key(0x09)
        time.sleep(0.5)

        # Paste Password into Password field
        print("Pasting Password into Password field...")
        system_automation.paste_into_focused_input("Janat#$61")
        time.sleep(1.0)

        # Submit with Enter
        print("Sending Enter...")
        system_automation.send_key(0x0D)
        time.sleep(4.0)

        print("Finished sequence!")
finally:
    subprocess.run(["taskkill", "/F", "/T", "/PID", str(proc.pid)], capture_output=True)

