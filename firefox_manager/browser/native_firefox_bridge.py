"""
Native Firefox Bridge.
Syncs Subwey multi-profiles with Windows native Firefox's profiles.ini.
Allows any created profile to be launched directly from standard Firefox shortcuts,
about:profiles, or Windows Start Menu without needing our tool active.
"""

import os
import configparser
from pathlib import Path
from typing import Optional, List, Dict, Any

from firefox_manager.config.settings import settings
from firefox_manager.security.audit_logger import audit_logger


class NativeFirefoxBridge:
    """Manages synchronization between Subwey profiles and native Firefox profiles.ini."""

    def __init__(self):
        self.appdata = Path(os.environ.get("APPDATA", ""))
        self.firefox_dir = self.appdata / "Mozilla" / "Firefox"
        self.profiles_ini_path = self.firefox_dir / "profiles.ini"

    def is_available(self) -> bool:
        """Check if native Firefox configuration directory exists."""
        return self.firefox_dir.exists()

    def _read_ini(self) -> configparser.RawConfigParser:
        config = configparser.RawConfigParser(strict=False)
        config.optionxform = lambda opt: opt  # Preserve case-sensitivity
        if self.profiles_ini_path.exists():
            config.read(self.profiles_ini_path, encoding="utf-8")
        return config

    def _write_ini(self, config: configparser.RawConfigParser) -> None:
        self.firefox_dir.mkdir(parents=True, exist_ok=True)
        with open(self.profiles_ini_path, "w", encoding="utf-8") as f:
            config.write(f)

    def register_profile(self, profile_name: str, absolute_profile_dir: Path) -> bool:
        """
        Register a custom profile in native Firefox profiles.ini with IsRelative=0.
        """
        if not self.is_available():
            return False

        try:
            config = self._read_ini()

            # Check if already registered
            for section in config.sections():
                if section.lower().startswith("profile"):
                    sec_name = config.get(section, "Name", fallback="")
                    sec_path = config.get(section, "Path", fallback="")
                    if sec_name == profile_name or sec_path == str(absolute_profile_dir):
                        # Update path
                        config.set(section, "Name", profile_name)
                        config.set(section, "IsRelative", "0")
                        config.set(section, "Path", str(absolute_profile_dir.resolve()))
                        self._write_ini(config)
                        self._create_launch_batch(profile_name, absolute_profile_dir)
                        return True

            # Find next Profile index
            existing_indices = []
            for section in config.sections():
                if section.lower().startswith("profile") and len(section) > 7:
                    try:
                        idx = int(section[7:])
                        existing_indices.append(idx)
                    except ValueError:
                        pass

            next_idx = max(existing_indices) + 1 if existing_indices else 2
            new_sec = f"Profile{next_idx}"

            config.add_section(new_sec)
            config.set(new_sec, "Name", profile_name)
            config.set(new_sec, "IsRelative", "0")
            config.set(new_sec, "Path", str(absolute_profile_dir.resolve()))

            self._write_ini(config)
            self._create_launch_batch(profile_name, absolute_profile_dir)

            audit_logger.log(
                agent_name="NativeFirefoxBridge",
                action="PROFILE_REGISTERED_NATIVE",
                target=profile_name,
                details=f"Registered in native Firefox profiles.ini as {new_sec}",
            )
            return True
        except Exception as e:
            audit_logger.log(
                agent_name="NativeFirefoxBridge",
                action="REGISTER_FAILED",
                target=profile_name,
                details=str(e),
            )
            return False

    def unregister_profile(self, profile_name: str) -> bool:
        """Remove profile registration from native Firefox profiles.ini."""
        if not self.is_available() or not self.profiles_ini_path.exists():
            return False

        try:
            config = self._read_ini()
            removed = False

            for section in config.sections():
                if section.lower().startswith("profile"):
                    sec_name = config.get(section, "Name", fallback="")
                    if sec_name == profile_name:
                        config.remove_section(section)
                        removed = True

            if removed:
                self._write_ini(config)
                audit_logger.log(
                    agent_name="NativeFirefoxBridge",
                    action="PROFILE_UNREGISTERED_NATIVE",
                    target=profile_name,
                    details="Unregistered from native Firefox profiles.ini",
                )
            return removed
        except Exception:
            return False

    def _create_launch_batch(self, profile_name: str, absolute_profile_dir: Path) -> None:
        """Generate a 1-click Windows batch file to launch directly in native Firefox."""
        try:
            firefox_bin = settings.firefox_binary or Path(r"C:\Program Files\Mozilla Firefox\firefox.exe")
            bat_path = absolute_profile_dir / f"Launch_{profile_name}.bat"
            content = f'@echo off\nstart "" "{firefox_bin}" -P "{profile_name}"\n'
            bat_path.write_text(content, encoding="utf-8")
        except Exception:
            pass


native_firefox_bridge = NativeFirefoxBridge()
