"""
Configuration and settings module for Firefox Multi-Profile Manager.
Validates all system paths, execution limits, and Firefox runtime flags.

Paths are derived from this file's location (the project root), never
from os.getcwd(), so data/profiles/logs land in the same place no matter
where the program is launched from.
"""

from pathlib import Path
import os
import sys
from typing import Optional, List
from pydantic import BaseModel, Field, field_validator

# Project root: config/ -> firefox_manager/ -> project root.
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent


def _project_base_dir() -> Path:
    override = os.environ.get("FIREFOX_MANAGER_BASE_DIR", "").strip()
    if override:
        return Path(override).expanduser().resolve()
    return PROJECT_ROOT


def get_default_firefox_path() -> Optional[str]:
    """Auto-detect standard Firefox installation path on Windows."""
    env_path = os.environ.get("FIREFOX_BINARY", "").strip()
    if env_path and os.path.isfile(env_path):
        return str(Path(env_path).resolve())
    if sys.platform != "win32":
        return None
    candidates = [
        os.path.expandvars(r"%ProgramFiles%\Mozilla Firefox\firefox.exe"),
        os.path.expandvars(r"%ProgramFiles(x86)%\Mozilla Firefox\firefox.exe"),
        os.path.expandvars(r"%LOCALAPPDATA%\Mozilla Firefox\firefox.exe"),
        r"C:\Program Files\Mozilla Firefox\firefox.exe",
        r"C:\Program Files (x86)\Mozilla Firefox\firefox.exe",
    ]
    for candidate in candidates:
        if candidate and os.path.isfile(candidate):
            return str(Path(candidate).resolve())
    return None


class AppSettings(BaseModel):
    """Application-wide settings with Pydantic validation."""

    app_name: str = "Firefox Multi-Profile Manager"
    app_version: str = "1.0.0"
    base_dir: Path = Field(default_factory=_project_base_dir)

    # Storage paths (derived from base_dir, not the current working directory)
    data_dir: Path = Field(default_factory=lambda: _project_base_dir() / "data")
    profiles_dir: Path = Field(default_factory=lambda: _project_base_dir() / "profiles")
    logs_dir: Path = Field(default_factory=lambda: _project_base_dir() / "logs")
    backups_dir: Path = Field(default_factory=lambda: _project_base_dir() / "backups")
    database_file: str = "firefox_manager.db"

    # Firefox executable configuration. May be None on a machine without
    # Firefox; callers must use require_firefox_binary() instead of
    # assuming it is set. Nothing raises at import time for this.
    firefox_binary_path: Optional[str] = Field(default_factory=get_default_firefox_path)

    # Concurrency and resource thresholds
    max_concurrent_profiles: int = Field(default=10, ge=1, le=50)
    cpu_alert_threshold_percent: float = Field(default=85.0, ge=10.0, le=100.0)
    memory_alert_threshold_mb: float = Field(default=4096.0, ge=256.0, le=32768.0)

    # Process management intervals (seconds)
    monitor_interval_seconds: float = Field(default=2.0, ge=0.5, le=60.0)
    session_check_interval_seconds: float = Field(default=30.0, ge=5.0, le=3600.0)
    process_timeout_seconds: float = Field(default=15.0, ge=2.0, le=120.0)
    crash_recovery_retries: int = Field(default=3, ge=0, le=10)

    # Database backup
    auto_backup_enabled: bool = True
    backup_retention_count: int = Field(default=5, ge=1, le=50)

    # Native Firefox profile default preferences
    default_prefs: dict = Field(
        default_factory=lambda: {
            "browser.shell.checkDefaultBrowser": False,
            "browser.startup.homepage_override.mstone": "ignore",
            "browser.aboutConfig.showWarning": False,
            "browser.warnOnQuit": False,
            "browser.sessionstore.resume_from_crash": False,
            "browser.sessionstore.restore_on_demand": False,
            "browser.sessionstore.resume_session_once": False,
            "browser.sessionstore.max_resumed_crashes": -1,
            "browser.sessionstore.resuming_after_crash": False,
            "browser.sessionstore.interval": 15000,
            "browser.tabs.warnOnClose": False,
            "browser.warnOnQuitShortcut": False,
            "browser.startup.couldRestoreSession.count": -1,
            "privacy.sanitize.sanitizeOnShutdown": False,
            "network.cookie.lifetimePolicy": 0,  # Keep cookies normally
            "dom.webnotifications.enabled": True,
            "toolkit.telemetry.enabled": False,
            "toolkit.telemetry.unified": False,
            "datareporting.healthreport.uploadEnabled": False,
            "app.update.auto": False,
            "app.update.enabled": False,
            # Disable autofill / external browser import popups (e.g. Edge password import)
            "signon.management.page.fileImport.enabled": False,
            "signon.autofillForms": False,
            "signon.showAutoCompleteFooter": False,
            "signon.rememberSignons": False,
            "signon.suggestImportCount": 0,
            # Was True: that flag claims passwords were already imported
            # from Edge and can trigger import prompts. It must be False.
            "signon.importedFromEdge": False,
            "browser.migrate.content-modal.import-all.enabled": False,
            "browser.migrate.interactions.passwords": False,
            "browser.migrate.edge.enabled": False,
            "browser.migrate.chrome.enabled": False,
            "browser.urlbar.suggest.history": False,
            "browser.urlbar.suggest.bookmark": False,
            "browser.urlbar.suggest.openpage": False,
        }
    )

    @field_validator("profiles_dir", "logs_dir", "backups_dir", "data_dir")
    @classmethod
    def _normalise_dir(cls, v: Path) -> Path:
        # Validation only: do NOT create directories here. Directory
        # creation is an explicit, idempotent step in ensure_all_dirs(),
        # called once at startup. Creating them as a side effect of
        # validation meant merely importing settings touched the disk
        # (including in tests).
        return Path(v).expanduser().resolve()

    @property
    def db_path(self) -> Path:
        return self.data_dir / self.database_file

    def require_firefox_binary(self) -> str:
        """Return the Firefox binary path, or raise a clear error.

        Use this at the point Firefox is actually launched, not at
        import time, so `--status` / `--help` / tests still work on a
        machine without Firefox installed.
        """
        env_path = os.environ.get("FIREFOX_BINARY", "").strip()
        candidate = env_path or self.firefox_binary_path
        if candidate and os.path.isfile(candidate):
            return str(Path(candidate).resolve())
        raise FileNotFoundError(
            "Firefox executable could not be found. Install Firefox, or set "
            "the FIREFOX_BINARY environment variable to the full path of "
            "firefox.exe."
        )

    def ensure_all_dirs(self) -> None:
        """Idempotently create all storage directories. Safe to call twice."""
        for d in (self.data_dir, self.profiles_dir, self.logs_dir, self.backups_dir):
            d.mkdir(parents=True, exist_ok=True)


# Singleton instance
settings = AppSettings()
settings.ensure_all_dirs()
