"""
Agent 4: Browser Monitor Agent.
Continuously monitors running Firefox processes, collects CPU & memory metrics,
detects crashes or high resource consumption, and reports snapshots to the orchestrator.
"""

import time
import threading
from typing import Dict, Any, List
from datetime import datetime, timezone

from firefox_manager.config.settings import settings
from firefox_manager.database.database import db
from firefox_manager.database.models import ProcessMetricRecord, AuditSeverity, ProfileStatus
from firefox_manager.core.process_manager import process_manager
from firefox_manager.core.profile_manager import profile_manager
from firefox_manager.security.audit_logger import audit_logger


class MonitoringAgent:
    """Background monitoring agent for system resources and browser health."""

    name = "MonitoringAgent"

    def __init__(self, orchestrator=None):
        self.orchestrator = orchestrator
        self._running = False
        self._thread: threading.Thread = None

    def start(self) -> None:
        """Start background monitoring loop."""
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(target=self._monitor_loop, daemon=True, name="BrowserMonitorThread")
        self._thread.start()
        audit_logger.log(
            agent_name=self.name,
            action="MONITORING_STARTED",
            details="Process and resource monitoring loop initialized.",
        )

    def stop(self) -> None:
        """Stop background monitoring loop."""
        self._running = False
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=2.0)

    def sample_now(self) -> Dict[str, Dict[str, float]]:
        """Perform an immediate sample of all active profile metrics."""
        metrics_by_profile = {}
        now_iso = datetime.now(timezone.utc).isoformat()

        # Reconcile DB vs live OS processes
        profile_manager.sync_active_profiles()

        active_metrics = process_manager.get_all_active_metrics()
        for profile_id, (cpu, mem) in active_metrics.items():
            pid = process_manager.get_pid(profile_id)
            if not pid:
                continue

            metric = ProcessMetricRecord(
                profile_id=profile_id,
                pid=pid,
                cpu_percent=cpu,
                memory_mb=mem,
                recorded_at=now_iso,
            )
            try:
                db.record_process_metric(metric)
            except Exception:
                pass

            metrics_by_profile[profile_id] = {
                "cpu_percent": cpu,
                "memory_mb": mem,
                "pid": pid,
            }

            # Check threshold alerts
            if cpu > settings.cpu_alert_threshold_percent:
                audit_logger.log(
                    agent_name=self.name,
                    action="HIGH_CPU_WARNING",
                    target=profile_id,
                    details=f"High CPU utilization: {cpu}% (threshold: {settings.cpu_alert_threshold_percent}%)",
                    severity=AuditSeverity.WARNING,
                )

            if mem > settings.memory_alert_threshold_mb:
                audit_logger.log(
                    agent_name=self.name,
                    action="HIGH_MEMORY_WARNING",
                    target=profile_id,
                    details=f"High memory consumption: {mem} MB (threshold: {settings.memory_alert_threshold_mb} MB)",
                    severity=AuditSeverity.WARNING,
                )

        if self.orchestrator:
            self.orchestrator.notify_event("METRICS_UPDATED", metrics_by_profile)

        return metrics_by_profile

    def _monitor_loop(self) -> None:
        """Continuous background loop."""
        while self._running:
            try:
                self.sample_now()
            except Exception as e:
                audit_logger.log(
                    agent_name=self.name,
                    action="MONITORING_LOOP_ERROR",
                    details=str(e),
                    severity=AuditSeverity.ERROR,
                )
            time.sleep(settings.monitor_interval_seconds)

