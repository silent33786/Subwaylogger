"""
Central Orchestrator Layer.
Acts as the central coordination hub interconnecting all 8 specialized agents:
ProfileAgent, SessionManager, AccountAgent, MonitoringAgent,
SecurityAgent, RecoveryAgent, AuditLogger, and GUIAgent.
"""

from typing import Dict, Any, Callable, List, Optional
from datetime import datetime, timezone

from firefox_manager.config.settings import settings
from firefox_manager.database.database import db
from firefox_manager.database.models import ProfileStatus, AccountStatus, AuditSeverity
from firefox_manager.security.audit_logger import audit_logger, AuditLogger
from firefox_manager.core.process_manager import process_manager, ProcessManager
from firefox_manager.core.session_manager import session_manager, SessionManager
from firefox_manager.browser.profile_storage import profile_storage, ProfileStorageManager
from firefox_manager.agents.profile_agent import ProfileAgent
from firefox_manager.agents.account_agent import AccountAgent
from firefox_manager.agents.security_agent import SecurityAgent
from firefox_manager.agents.recovery_agent import RecoveryAgent
from firefox_manager.agents.monitoring_agent import MonitoringAgent
from firefox_manager.authentication.verification_handler import verification_handler, VerificationHandler


class Orchestrator:
    """Central Controller and Message Bus for Multi-Agent Architecture."""

    def __init__(self):
        # Instantiate Agents with back-reference to Orchestrator
        self.profile_agent = ProfileAgent(orchestrator=self)
        self.session_manager = session_manager
        self.account_agent = AccountAgent(orchestrator=self)
        self.monitoring_agent = MonitoringAgent(orchestrator=self)
        self.security_agent = SecurityAgent(orchestrator=self)
        self.recovery_agent = RecoveryAgent(orchestrator=self)
        self.logging_agent = audit_logger
        self.verification_handler = verification_handler

        self._event_subscribers: Dict[str, List[Callable[[str, Any], None]]] = {}

    def subscribe_event(self, event_name: str, callback: Callable[[str, Any], None]) -> None:
        """Register event listener for orchestrator events."""
        if event_name not in self._event_subscribers:
            self._event_subscribers[event_name] = []
        if callback not in self._event_subscribers[event_name]:
            self._event_subscribers[event_name].append(callback)

    def notify_event(self, event_name: str, payload: Any = None) -> None:
        """Broadcast an event across agents and GUI listeners."""
        # Wildcard subscribers
        for cb in self._event_subscribers.get("*", []):
            try:
                cb(event_name, payload)
            except Exception:
                pass

        # Specific event subscribers
        for cb in self._event_subscribers.get(event_name, []):
            try:
                cb(event_name, payload)
            except Exception:
                pass

    def initialize(self) -> None:
        """
        System startup routine:
        1. Clean up stale lock files from any prior abnormal shutdown.
        2. Sync profile records with current OS processes.
        3. Evaluate existing account sessions.
        4. Start background monitoring agent.
        """
        self.logging_agent.log(
            agent_name="Orchestrator",
            action="SYSTEM_STARTUP",
            details="Initializing Firefox Multi-Profile Management Platform.",
        )

        # 1. Clean stale locks
        cleaned_locks = self.recovery_agent.clean_all_stale_locks()
        if cleaned_locks > 0:
            self.logging_agent.log(
                agent_name="Orchestrator",
                action="STARTUP_LOCKS_CLEANED",
                details=f"Cleared {cleaned_locks} orphaned locks.",
            )

        # 2. Reconcile database with live processes
        from firefox_manager.core.profile_manager import profile_manager
        profile_manager.sync_active_profiles()

        # 3. Clean any orphaned junk folders on disk
        cleaned_junk = profile_manager.clean_orphaned_profiles()
        if cleaned_junk > 0:
            self.logging_agent.log(
                agent_name="Orchestrator",
                action="STARTUP_JUNK_PURGED",
                details=f"Permanently wiped {cleaned_junk} orphaned profile folder(s) from system.",
            )

        # 4. Check session expiration
        self.session_manager.evaluate_account_sessions()

        # 4. Start resource monitoring agent
        self.monitoring_agent.start()

    def shutdown(self) -> None:
        """
        System shutdown routine:
        1. Stop monitoring agent.
        2. Gracefully terminate all active browser processes.
        3. Create point-in-time database backup.
        """
        self.logging_agent.log(
            agent_name="Orchestrator",
            action="SYSTEM_SHUTDOWN",
            details="Graceful shutdown initiated.",
        )

        self.monitoring_agent.stop()
        process_manager.shutdown_all()

        if settings.auto_backup_enabled:
            self.recovery_agent.backup_database()

    def get_dashboard_summary(self) -> Dict[str, Any]:
        """
        Compute real-time platform statistics for the GUI dashboard:
        - Total Profiles
        - Active Profiles
        - Inactive Profiles
        - Connected Accounts
        - Active Processes
        - Pending Verifications
        - Total Resource Metrics
        """
        profiles = db.list_profiles()
        accounts = db.list_accounts()
        pending_verifications = self.verification_handler.get_pending_requests()

        total_profiles = len(profiles)
        active_profiles = sum(1 for p in profiles if p.is_active or process_manager.is_running(p.id))
        inactive_profiles = total_profiles - active_profiles

        active_metrics = process_manager.get_all_active_metrics()
        total_cpu = sum(m[0] for m in active_metrics.values())
        total_memory_mb = sum(m[1] for m in active_metrics.values())

        return {
            "total_profiles": total_profiles,
            "active_profiles": active_profiles,
            "inactive_profiles": inactive_profiles,
            "connected_accounts": len(accounts),
            "active_processes": len(active_metrics),
            "pending_verifications": len(pending_verifications),
            "total_cpu_percent": round(total_cpu, 1),
            "total_memory_mb": round(total_memory_mb, 1),
            "profiles": profiles,
            "accounts": accounts,
            "metrics": active_metrics,
        }


# Global orchestrator instance
orchestrator = Orchestrator()

