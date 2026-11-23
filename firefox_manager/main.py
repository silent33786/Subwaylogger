"""
Main Application Entry Point.
Launches the Firefox Multi-Profile Manager in GUI desktop mode or CLI mode.
"""

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


def run_cli(args) -> int:
    """Execute command-line operations."""
    orchestrator.initialize()

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

        if args.backup:
            bk = orchestrator.recovery_agent.backup_database()
            print(f"Database backed up to: {bk}")
            return 0

        if args.fb_login:
            if not args.profile or not args.uid or not args.password:
                print("Error: --fb-login requires --profile <ID>, --uid <UID>, and --password <PWD>")
                return 1
            from firefox_manager.authentication.system_automation import system_automation
            res = system_automation.run_facebook_login_system_level(
                profile_id=args.profile,
                username_or_uid=args.uid,
                password=args.password,
                page_load_delay=args.delay or 6.0,
                status_callback=lambda msg: print(f"[*] {msg}"),
            )
            print(f"Result: {res}")
            return 0

        if args.batch_fb:
            from firefox_manager.authentication.system_automation import system_automation
            lines = []
            if os.path.isfile(args.batch_fb):
                lines = Path(args.batch_fb).read_text(encoding="utf-8").splitlines()
            else:
                lines = args.batch_fb.split(";")
            print(f"Loaded {len(lines)} accounts for batch auto-profile generation & login...")
            res = system_automation.run_batch_facebook_automation(
                account_lines=lines,
                page_load_delay=args.delay or 6.0,
                status_callback=lambda msg: print(f"[*] {msg}"),
            )
            print(f"Batch Result: {res}")
            return 0

    finally:
        orchestrator.shutdown()

    return 0


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
    parser.add_argument("--url", type=str, default=None, help="Initial URL when launching profile")
    parser.add_argument("--backup", action="store_true", help="Trigger immediate database backup")
    parser.add_argument("--fb-login", action="store_true", help="Run system-level Facebook automated login")
    parser.add_argument("--batch-fb", type=str, metavar="FILE_OR_STR", help="Path to accounts list file or semicolon-delimited string")
    parser.add_argument("--profile", type=str, help="Profile ID for automation")
    parser.add_argument("--uid", type=str, help="Facebook UID or Email")
    parser.add_argument("--password", type=str, help="Facebook Password")
    parser.add_argument("--delay", type=float, default=6.0, help="Seconds to wait for page load before typing")

    args = parser.parse_args()

    # If any CLI action was requested, run CLI mode
    if (args.cli or args.status or args.list_profiles or args.create_profile or
        args.launch_profile or args.stop_profile or args.backup or args.fb_login or args.batch_fb):
        return run_cli(args)

    return run_gui()


if __name__ == "__main__":
    sys.exit(main())

