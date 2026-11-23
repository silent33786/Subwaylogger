"""
Configuration and settings module for Firefox Multi-Profile Manager.
Validates all system paths, execution limits, and Firefox runtime flags.
"""

from pathlib import Path
import os
import sys
from typing import Optional, List
from pydantic import BaseModel, Field, field_validator


def get_default_firefox_path() -> Optional[str]:
    """Auto-detect standard Firefox installation path on Windows."""
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
    base_dir: Path = Field(default_factory=lambda: Path(os.getcwd()).resolve())
    
    # Storage paths
    data_dir: Path = Field(default_factory=lambda: Path(os.getcwd()).resolve() / "data")
    profiles_dir: Path = Field(default_factory=lambda: Path(os.getcwd()).resolve() / "profiles")
    logs_dir: Path = Field(default_factory=lambda: Path(os.getcwd()).resolve() / "logs")
    backups_dir: Path = Field(default_factory=lambda: Path(os.getcwd()).resolve() / "backups")
    database_file: str = "firefox_manager.db"

    # Firefox executable configuration
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
            "signon.importedFromEdge": True,
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
    def ensure_directory_exists(cls, v: Path) -> Path:
        """Create directories if they do not exist."""
        v.mkdir(parents=True, exist_ok=True)
        return v

    @property
    def db_path(self) -> Path:
        return self.data_dir / self.database_file

    def ensure_all_dirs(self) -> None:
        """Helper to guarantee all directories are initialized on disk."""
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.profiles_dir.mkdir(parents=True, exist_ok=True)
        self.logs_dir.mkdir(parents=True, exist_ok=True)
        self.backups_dir.mkdir(parents=True, exist_ok=True)


# Singleton instance
settings = AppSettings()
settings.ensure_all_dirs()

