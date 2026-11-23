"""
Dedicated Profile Logging System.
Maintains individual, persistent log files for each Firefox profile under logs/profiles/.
Enables fine-grained debugging of automation steps, click coordinates, visual landmarks,
and security checkpoints.
"""

import os
import time
from pathlib import Path
from datetime import datetime, timezone
from typing import Optional, List

from firefox_manager.config.settings import settings


LOGS_BASE_DIR = Path("logs").resolve()
PROFILES_LOGS_DIR = LOGS_BASE_DIR / "profiles"


class ProfileLogger:
    """Manages per-profile dedicated log files."""

    def __init__(self):
        self._ensure_dirs()

    def _ensure_dirs(self) -> None:
        """Create log directories if they don't exist."""
        PROFILES_LOGS_DIR.mkdir(parents=True, exist_ok=True)

    def get_profile_log_path(self, profile_id_or_name: str) -> Path:
        """Get absolute path to a profile's log file."""
        self._ensure_dirs()
        safe_name = "".join(c if c.isalnum() or c in ("-", "_") else "_" for c in profile_id_or_name)
        return PROFILES_LOGS_DIR / f"{safe_name}.log"

    def log(
        self,
        profile_id_or_name: str,
        message: str,
        level: str = "INFO",
        extra: Optional[dict] = None,
    ) -> None:
        """Write timestamped entry to profile's specific log file."""
        try:
            log_path = self.get_profile_log_path(profile_id_or_name)
            now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
            line = f"[{now_str}] [{level.upper()}] {message}"
            if extra:
                line += f" | Details: {extra}"
            line += "\n"

            with open(log_path, "a", encoding="utf-8", errors="replace") as f:
                f.write(line)
        except Exception:
            pass

    def read_logs(self, profile_id_or_name: str, max_lines: int = 150) -> List[str]:
        """Read recent log lines for debugging in the GUI."""
        log_path = self.get_profile_log_path(profile_id_or_name)
        if not log_path.exists():
            return [f"No log file found at {log_path}"]
        try:
            with open(log_path, "r", encoding="utf-8", errors="replace") as f:
                lines = f.readlines()
            return lines[-max_lines:]
        except Exception as e:
            return [f"Error reading log file: {e}"]

    def get_logs_dir(self) -> Path:
        """Return base profiles logs directory."""
        self._ensure_dirs()
        return PROFILES_LOGS_DIR


profile_logger = ProfileLogger()
