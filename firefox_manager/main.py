"""
Main Application Entry Point.
Launches the Firefox Multi-Profile Manager in GUI desktop mode or CLI mode.

Security: there is deliberately NO --password argument. A password must
never appear on a command line (shell history / process list). Facebook
login takes the password from the FB_PASSWORD environment variable, or
prompts securely with getpass() if it is not set.
"""

import getpass
import sys
import os
import argparse
import signal
from pathlib import Path

# Ensure root package is in sys.path
BASE_DIR = Path(__file__).resolve().parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

# High-DPI environment variables for Qt before QApplication
os.environ["QT_ENABLE_HIGHDPI_SCALING"] = "1"
os.environ["QT_AUTO_SCREEN_SCALE_FACTOR"] = "1"

from firefox_manager.config.settings import settings
from firefox_manager.core.orchestrator import orchestrator


# Register Windows Console Ctrl Handler to cleanly intercept Ctrl+C in terminal
_console_handler_ref = None
if sys.platform == "win32":
    import ctypes
    from ctypes import wintypes

    PHANDLER_ROUTINE = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.DWORD)

    def _console_ctrl_handler(dwCtrlType: int) -> bool:
        if dwCtrlType in (0, 2):  # CTRL_C_EVENT or CTRL_CLOSE_EVENT
            print("\n[Ctrl+C detected] Terminating all background processes and profiles cleanly...")
            try:
                orchestrator.shutdown()
            except Exception:
                pass
            os._exit(0)
            return True
        return False

    _console_handler_ref = PHANDLER_ROUTINE(_console_ctrl_handler)
    ctypes.windll.kernel32.SetConsoleCtrlHandler(_console_handler_ref, True)


def _resolve_password() -> str:
    """Password only from FB_PASSWORD env var or a hidden getpass prompt."""
    password = os.environ.get("FB_PASSWORD", "")
    if password:
        return password
    return getpass.getpass("Facebook password (hidden, not echoed): ")


def _resolve_delay(args) -> float:
    # `args.delay or 6.0` was a bug: an explicit --delay 0 became 6.0.
    # None means "not given" -> default 6.0; 0.0 is a real, honoured value.
    return 6.0 if args.delay is None else args.delay


def run_cli(args) -> int:
    """Execute command-line operations. Returns a process exit code."""
    try:
        orchestrator.initialize()
    except Exception as exc:
        print(f"Error: failed to initialise: {exc}")
        return 1

    try:
        if args.status:
            summary = orchestrator.get_dashboard_summary()
            print("=" * 60)
            print(f" {settings.app_name} Status")
            print("=" * 60)
            print(f"Total Profiles:       {summary['total_profiles']}")
            print(f"Active Profiles:      {summary['active_profiles']}")
            print(f"Inactive Profiles:    {summary['inactive_profiles']}")
            print(f"Connected Accounts:   {summary['connected_accounts']}")
            print(f"Total CPU / Memory:   {summary['total_cpu_percent']}% / {summary['total_memory_mb']} MB")
            print("=" * 60)
            return 0

        if args.list_profiles:
            profiles = orchestrator.profile_agent.list_profiles()
            print(f"\nManaged Profiles ({len(profiles)}):")
            for p in profiles:
                print(f" - [{p.status.value.upper()}] {p.name} (ID: {p.id}) Dir: {p.directory_name}")
            return 0

        if args.create_profile:
            p = orchestrator.profile_agent.create_profile(name=args.create_profile)
            print(f"Successfully created profile '{p.name}' (ID: {p.id})")
            return 0

        if args.launch_profile:
            pid = orchestrator.profile_agent.launch_profile(args.launch_profile, initial_url=args.url)
            print(f"Launched profile '{args.launch_profile}' with PID {pid}")
            return 0

        if args.stop_profile:
            orchestrator.profile_agent.stop_profile(args.stop_profile)
            print(f"Stopped profile '{args.stop_profile}'")
            return 0

        if args.delete_profile:
            deleted = orchestrator.profile_agent.delete_profile(args.delete_profile)
            if deleted:
                print(f"Deleted profile '{args.delete_profile}' (database record and files).")
                return 0
            print(f"Error: profile '{args.delete_profile}' not found.")
            return 1

        if args.backup:
            bk = orchestrator.recovery_agent.backup_database()
            print(f"Database backed up to: {bk}")
            return 0

        if args.fb_login:
            if not args.profile or not args.uid:
                print("Error: --fb-login requires --profile <ID> and --uid <UID-or-email>")
                return 1
            password = _resolve_password()
            if not password:
                print("Error: no password provided.")
                return 1
            try:
                from firefox_manager.authentication.system_automation import system_automation
                res = system_automation.run_facebook_login_system_level(
                    profile_id=args.profile,
                    username_or_uid=args.uid,
                    password=password,
                    page_load_delay=_resolve_delay(args),
                    status_callback=lambda msg: print(f"[*] {msg}"),
                )
            finally:
                password = ""
            print(f"Result: success={res.get('success')} home_page_reached={res.get('home_page_reached')} message={res.get('message')}")
            return 0 if res.get("success") else 1

        if args.batch_fb:
            # --batch-fb accepts ONLY a file path. A semicolon-delimited
            # string of credentials on the command line is refused.
            batch_path = Path(args.batch_fb)
            if not batch_path.is_file():
                print(f"Error: --batch-fb requires a file path, not inline credentials: {args.batch_fb}")
                return 1
            lines = batch_path.read_text(encoding="utf-8").splitlines()
            print(f"Loaded {len(lines)} lines for batch auto-profile generation & login...")
            from firefox_manager.authentication.system_automation import system_automation
            res = system_automation.run_batch_facebook_automation(
                account_lines=lines,
                page_load_delay=_resolve_delay(args),
                status_callback=lambda msg: print(f"[*] {msg}"),
            )
            print(f"Batch Result: {res.get('succeeded')}/{res.get('total')} succeeded.")
            return 0 if res.get("succeeded") == res.get("total") and res.get("total") else 1

        # No recognised action (should not happen - main() guards this).
        print("Error: no CLI action given. Use --help.")
        return 2
    except Exception as exc:
        # Clean error + exit code 1 instead of a raw traceback.
        print(f"Error: {exc}")
        return 1
    finally:
        try:
            orchestrator.shutdown()
        except Exception:
            pass


def run_gui() -> int:
    """Launch PySide6 GUI Dashboard."""
    from PySide6.QtWidgets import QApplication
    from PySide6.QtCore import Qt, QTimer
    from firefox_manager.gui.dashboard import DashboardWindow

    # High DPI scaling
    QApplication.setHighDpiScaleFactorRoundingPolicy(
        Qt.HighDpiScaleFactorRoundingPolicy.PassThrough
    )

    app = QApplication(sys.argv)
    app.setApplicationName(settings.app_name)
    app.setApplicationVersion(settings.app_version)
    app.aboutToQuit.connect(orchestrator.shutdown)

    # Periodic timer to allow Python to process SIGINT (Ctrl+C) while Qt event loop runs
    sigint_timer = QTimer()
    sigint_timer.timeout.connect(lambda: None)
    sigint_timer.start(200)

    signal.signal(signal.SIGINT, lambda sig, frame: app.quit())

    window = DashboardWindow()
    window.show()

    return app.exec()


def main() -> int:
    parser = argparse.ArgumentParser(description=f"{settings.app_name} - Native Firefox Orchestration")
    parser.add_argument("--cli", action="store_true", help="Run in CLI mode without GUI")
    parser.add_argument("--status", action="store_true", help="Print real-time status summary")
    parser.add_argument("--list-profiles", action="store_true", help="List all managed profiles")
    parser.add_argument("--create-profile", type=str, metavar="NAME", help="Create a new profile with given name")
    parser.add_argument("--launch-profile", type=str, metavar="ID", help="Launch profile by ID or Name")
    parser.add_argument("--stop-profile", type=str, metavar="ID", help="Stop profile by ID")
    parser.add_argument("--delete-profile", type=str, metavar="ID", help="Permanently delete profile by ID (database record and files on disk)")
    parser.add_argument("--url", type=str, default=None, help="Initial URL when launching profile")
    parser.add_argument("--backup", action="store_true", help="Trigger immediate database backup")
    parser.add_argument("--fb-login", action="store_true", help="Run system-level Facebook automated login (password via FB_PASSWORD env var or hidden getpass prompt - never on the command line)")
    parser.add_argument("--batch-fb", type=str, metavar="FILE", help="Path to a file with one UID:Password account per line")
    parser.add_argument("--profile", type=str, help="Profile ID for automation")
    parser.add_argument("--uid", type=str, help="Facebook UID or Email")
    parser.add_argument("--delay", type=float, default=None, help="Seconds to wait for page load before typing (default 6.0; 0 is honoured)")

    args = parser.parse_args()

    # If any CLI action was requested, run CLI mode
    if (args.cli or args.status or args.list_profiles or args.create_profile or
        args.launch_profile or args.stop_profile or args.delete_profile or
        args.backup or args.fb_login or args.batch_fb):
        return run_cli(args)

    # No CLI flags at all: launch the GUI (the original default).
    # The "no action" case that now returns 2 is --cli with no action,
    # handled inside run_cli() above.
    return run_gui()


if __name__ == "__main__":
    sys.exit(main())
