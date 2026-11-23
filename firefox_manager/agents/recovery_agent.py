"""
Agent 6: Recovery Agent.
Handles crash detection, cleans up stale profile locks, performs controlled restarts,
and triggers automatic database backups for disaster recovery.
"""

import time
from typing import Dict, Optional
from firefox_manager.config.settings import settings
from firefox_manager.database.database import db
from firefox_manager.database.models import ProfileStatus, AuditSeverity
from firefox_manager.browser.profile_storage import profile_storage
from firefox_manager.core.process_manager import process_manager
from firefox_manager.security.audit_logger import audit_logger


class RecoveryAgent:
    """Agent managing error recovery and controlled browser restarts."""

    name = "RecoveryAgent"

    def __init__(self, orchestrator=None):
        self.orchestrator = orchestrator
        self._crash_counts: Dict[str, int] = {}  # profile_id -> count
        # Register crash callback with process manager
        process_manager.register_crash_callback(self.handle_browser_crash)

    def handle_browser_crash(self, profile_id: str, exit_code: int) -> None:
        """
        Invoked when a Firefox process exits unexpectedly (non-zero or unplanned exit).
        Initiates controlled recovery if within configured retry limit.
        """
        profile = db.get_profile(profile_id)
        if not profile:
            return

        current_retries = self._crash_counts.get(profile_id, 0)

        audit_logger.log(
            agent_name=self.name,
            action="CRASH_DETECTED",
            target=profile.name,
            details=f"Profile '{profile.name}' crashed with code {exit_code}. Retry {current_retries + 1}/{settings.crash_recovery_retries}",
            severity=AuditSeverity.WARNING,
        )

        if current_retries < settings.crash_recovery_retries:
            self._crash_counts[profile_id] = current_retries + 1
            self._execute_recovery(profile.id, profile.directory_name, profile.name)
        else:
            # Exhausted retries
            self._crash_counts[profile_id] = 0
            db.update_profile_status(profile_id, ProfileStatus.ERROR, is_active=False)
            audit_logger.log(
                agent_name=self.name,
                action="RECOVERY_EXHAUSTED",
                target=profile.name,
                details=f"Exceeded max retries ({settings.crash_recovery_retries}). Profile marked as ERROR.",
                severity=AuditSeverity.CRITICAL,
            )
            if self.orchestrator:
                self.orchestrator.notify_event(
                    "RECOVERY_EXHAUSTED",
                    {"profile_id": profile_id, "name": profile.name},
                )

    def _execute_recovery(self, profile_id: str, directory_name: str, profile_name: str) -> None:
        """Clear locks and attempt restart."""
        db.update_profile_status(profile_id, ProfileStatus.RECOVERING, is_active=False)
        time.sleep(1.5)

        # 1. Clean up stale locks
        cleaned = profile_storage.remove_stale_lock(directory_name)

        audit_logger.log(
            agent_name=self.name,
            action="LOCK_CLEANUP",
            target=profile_name,
            details=f"Stale parent.lock cleared: {cleaned}",
        )

        # 2. Attempt restart via profile_manager
        try:
            from firefox_manager.core.profile_manager import profile_manager
            pid = profile_manager.launch_profile(profile_id)
            audit_logger.log(
                agent_name=self.name,
                action="RECOVERY_SUCCESS",
                target=profile_name,
                details=f"Profile '{profile_name}' successfully recovered and restarted with PID {pid}",
                severity=AuditSeverity.INFO,
            )
            if self.orchestrator:
                self.orchestrator.notify_event(
                    "PROFILE_RECOVERED", {"profile_id": profile_id, "pid": pid}
                )
        except Exception as e:
            audit_logger.log(
                agent_name=self.name,
                action="RECOVERY_FAILED",
                target=profile_name,
                details=f"Failed to relaunch after crash: {e}",
                severity=AuditSeverity.ERROR,
            )

    def clean_all_stale_locks(self) -> int:
        """Scan all profile folders and remove orphaned locks for stopped profiles."""
        cleaned_count = 0
        profiles = db.list_profiles()
        for p in profiles:
            if not process_manager.is_running(p.id):
                if profile_storage.is_profile_locked(p.directory_name):
                    if profile_storage.remove_stale_lock(p.directory_name):
                        cleaned_count += 1
        return cleaned_count

    def backup_database(self) -> str:
        """Perform automated database backup."""
        try:
            backup_path = db.backup_database()
            audit_logger.log(
                agent_name=self.name,
                action="DATABASE_BACKUP_COMPLETED",
                target=backup_path.name,
                details=f"Saved point-in-time snapshot to {backup_path}",
            )
            return str(backup_path)
        except Exception as e:
            audit_logger.log(
                agent_name=self.name,
                action="DATABASE_BACKUP_ERROR",
                details=str(e),
                severity=AuditSeverity.ERROR,
            )
            return ""

