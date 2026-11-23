"""
High-Level Firefox Profile Manager.
Orchestrates profile creation, launch, termination, restart, deletion,
and state synchronization with persistence.
"""

import re
import time
import uuid
from pathlib import Path
from typing import Optional, List, Dict, Any
from datetime import datetime, timezone

from firefox_manager.config.settings import settings
from firefox_manager.database.database import db
from firefox_manager.database.models import (
    ProfileRecord,
    ProfileStatus,
    AuditSeverity,
)
from firefox_manager.browser.profile_storage import profile_storage
from firefox_manager.browser.profile_packager import profile_packager
from firefox_manager.core.process_manager import process_manager
from firefox_manager.security.audit_logger import audit_logger


class ProfileManager:
    """Core profile lifecycle orchestrator."""

    def __init__(self):
        pass

    def _sanitize_name_to_directory(self, name: str, profile_id: str) -> str:
        """Create a safe unique filesystem directory name."""
        clean = re.sub(r"[^\w\-_\.]", "_", name.strip())
        short_id = profile_id[:8]
        return f"{clean}_{short_id}"

    def create_profile(
        self,
        name: str,
        custom_user_agent: Optional[str] = None,
        proxy_server: Optional[str] = None,
        notes: Optional[str] = "",
        tags: Optional[str] = "",
    ) -> ProfileRecord:
        """
        Create an independent, persistent Firefox profile.
        Guarantees isolation with unique directory and user.js preferences.
        """
        stripped_name = name.strip()
        if not stripped_name:
            raise ValueError("Profile name cannot be empty.")

        # Duplicate name prevention
        existing = db.get_profile_by_name(stripped_name)
        if existing:
            raise ValueError(f"A profile named '{stripped_name}' already exists.")

        profile_id = str(uuid.uuid4())
        directory_name = self._sanitize_name_to_directory(stripped_name, profile_id)

        # 1. Create physical profile directory and write initial user.js
        profile_storage.create_profile_directory(
            directory_name=directory_name,
            profile_id=profile_id,
            profile_name=stripped_name,
            custom_user_agent=custom_user_agent,
            proxy_server=proxy_server,
        )

        # 2. Persist record in SQLite
        record = ProfileRecord(
            id=profile_id,
            name=stripped_name,
            directory_name=directory_name,
            custom_user_agent=custom_user_agent,
            proxy_server=proxy_server,
            notes=notes or "",
            tags=tags or "",
            is_active=False,
            status=ProfileStatus.STOPPED,
            pid=None,
            disk_usage_bytes=profile_storage.calculate_disk_usage(directory_name),
        )

        db.create_profile(record)

        audit_logger.log(
            agent_name="ProfileManager",
            action="PROFILE_CREATED",
            target=stripped_name,
            details=f"ID: {profile_id}, Dir: {directory_name}",
        )
        return record

    def launch_profile(
        self, profile_id: str, initial_url: Optional[str] = None
    ) -> int:
        """
        Launch Firefox natively bound to the profile's dedicated directory.
        """
        profile = db.get_profile(profile_id)
        if not profile:
            raise ValueError(f"Profile with ID '{profile_id}' does not exist.")

        # Check if already active in ProcessManager
        if process_manager.is_running(profile_id):
            pid = process_manager.get_pid(profile_id)
            process_manager.bring_to_front(profile_id)
            return pid or 0

        # Check for profile lock
        if profile_storage.is_profile_locked(profile.directory_name):
            raise RuntimeError(
                f"Profile '{profile.name}' is currently locked by another process on disk."
            )

        profile_path = profile_storage.get_profile_path(profile.directory_name)
        now_iso = datetime.now(timezone.utc).isoformat()

        # Ensure latest anti-prompt & session preferences are applied to user.js
        try:
            profile_storage._write_profile_preferences(profile_path, proxy_server=profile.proxy_server)
        except Exception:
            pass

        # Update status to STARTING
        db.update_profile_status(profile_id, ProfileStatus.STARTING, is_active=False)

        try:
            pid = process_manager.launch_profile_process(
                profile_id=profile_id,
                directory_name=profile.directory_name,
                profile_path=profile_path,
                initial_url=initial_url,
            )

            # Update DB to RUNNING
            db.update_profile_status(
                profile_id=profile_id,
                status=ProfileStatus.RUNNING,
                is_active=True,
                pid=pid,
                last_launched_at=now_iso,
            )

            audit_logger.log(
                agent_name="ProfileManager",
                action="PROFILE_LAUNCHED",
                target=profile.name,
                details=f"PID: {pid}, URL: {initial_url or 'default'}",
            )
            return pid
        except Exception as e:
            db.update_profile_status(
                profile_id=profile_id, status=ProfileStatus.ERROR, is_active=False
            )
            audit_logger.log(
                agent_name="ProfileManager",
                action="PROFILE_LAUNCH_FAILED",
                target=profile.name,
                details=str(e),
                severity=AuditSeverity.ERROR,
            )
            raise

    def stop_profile(self, profile_id: str) -> bool:
        """Gracefully stop profile process and update status."""
        profile = db.get_profile(profile_id)
        if not profile:
            return False

        now_iso = datetime.now(timezone.utc).isoformat()
        db.update_profile_status(profile_id, ProfileStatus.STOPPING, is_active=True)

        stopped = process_manager.stop_profile_process(profile_id)

        # Update disk usage
        disk_usage = profile_storage.calculate_disk_usage(profile.directory_name)

        db.update_profile_status(
            profile_id=profile_id,
            status=ProfileStatus.STOPPED,
            is_active=False,
            pid=None,
            last_stopped_at=now_iso,
        )

        profile.disk_usage_bytes = disk_usage
        db.update_profile(profile)

        audit_logger.log(
            agent_name="ProfileManager",
            action="PROFILE_STOPPED",
            target=profile.name,
            details=f"Profile '{profile.name}' stopped. Disk usage: {disk_usage / 1024:.1f} KB",
        )
        return stopped

    def restart_profile(
        self, profile_id: str, initial_url: Optional[str] = None
    ) -> int:
        """Restart profile instance cleanly."""
        profile = db.get_profile(profile_id)
        if not profile:
            raise ValueError(f"Profile '{profile_id}' not found.")

        audit_logger.log(
            agent_name="ProfileManager",
            action="PROFILE_RESTARTING",
            target=profile.name,
            details="Stopping profile for restart...",
        )

        self.stop_profile(profile_id)
        time.sleep(1.0)  # Brief grace period for lock release

        # Ensure lock is completely cleared
        profile_storage.remove_stale_lock(profile.directory_name)

        return self.launch_profile(profile_id, initial_url)

    def delete_profile(self, profile_id: str, remove_disk_files: bool = True) -> bool:
        """
        Terminate and permanently delete profile from disk and database.
        Guarantees that files on disk are completely removed, preventing any junk buildup.
        """
        profile = db.get_profile(profile_id)
        if not profile:
            return False

        if process_manager.is_running(profile_id):
            process_manager.stop_profile_process(profile_id, timeout=2.0)
            time.sleep(1.5)  # Wait for Windows handles to release

        if remove_disk_files:
            files_removed = profile_storage.delete_profile_directory(profile.directory_name, max_retries=8)
            if not files_removed:
                raise RuntimeError(
                    f"Profile '{profile.name}' could not be deleted from disk because its files are currently locked by Windows. "
                    "Please ensure Firefox is closed and try again."
                )

        deleted = db.delete_profile(profile_id)

        # Unregister from native Firefox profiles.ini
        try:
            native_firefox_bridge.unregister_profile(profile.name)
        except Exception:
            pass

        audit_logger.log(
            agent_name="ProfileManager",
            action="PROFILE_DELETED",
            target=profile.name,
            details=f"Database record deleted: {deleted}. Permanent files wiped from system: True",
        )
        return deleted

    def clean_orphaned_profiles(self) -> int:
        """
        Scan profiles/ base directory and auto-import any manually dropped profile folders.
        Wipes only genuinely corrupted or empty unmapped directories.
        """
        # First: auto-sync any valid profile folders dropped from another PC
        try:
            profile_packager.auto_sync_dropped_profile_folders()
        except Exception:
            pass

        registered = {p.directory_name for p in db.list_profiles()}
        cleaned_count = 0

        if not settings.profiles_dir.exists():
            return 0

        for item in settings.profiles_dir.iterdir():
            if item.is_dir() and item.name not in registered:
                # Do not delete if it contains active profile signatures
                has_ff_files = any(
                    (item / f).exists()
                    for f in ("cookies.sqlite", "prefs.js", "user.js", "places.sqlite")
                )
                if has_ff_files:
                    continue

                audit_logger.log(
                    agent_name="ProfileManager",
                    action="CLEANING_ORPHANED_JUNK",
                    target=item.name,
                    details=f"Detected empty or corrupted unmapped folder '{item.name}'. Purging from disk.",
                )
                if profile_storage.delete_profile_directory(item.name, max_retries=6):
                    cleaned_count += 1

        return cleaned_count

    def sync_active_profiles(self) -> None:
        """
        Reconcile database records with actual live operating system processes.
        Detects profiles closed by user via browser window 'X' button or unexpected crash.
        """
        profiles = db.list_profiles()
        for p in profiles:
            is_proc_alive = process_manager.is_running(p.id)
            if p.is_active and not is_proc_alive:
                # Process exited without dashboard action
                now_iso = datetime.now(timezone.utc).isoformat()
                db.update_profile_status(
                    p.id,
                    ProfileStatus.STOPPED,
                    is_active=False,
                    pid=None,
                    last_stopped_at=now_iso,
                )
            elif not p.is_active and is_proc_alive:
                # Registered active in process manager
                pid = process_manager.get_pid(p.id)
                db.update_profile_status(p.id, ProfileStatus.RUNNING, is_active=True, pid=pid)


# Global profile manager
profile_manager = ProfileManager()

