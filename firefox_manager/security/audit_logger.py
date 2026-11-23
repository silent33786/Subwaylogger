"""
Audit Logger and Operational Logging Agent.
Maintains tamper-evident audit trails in the SQLite database and rotating log files.
Provides pub/sub callback mechanisms for real-time GUI stream updates.
"""

import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Optional, Callable, List
from datetime import datetime, timezone

from firefox_manager.config.settings import settings
from firefox_manager.database.database import db
from firefox_manager.database.models import AuditLogRecord, AuditSeverity


class AuditLogger:
    """Enterprise audit logger coordinating file logs and DB records."""

    def __init__(self, log_dir: Optional[Path] = None):
        self.log_dir = Path(log_dir or settings.logs_dir)
        self.log_dir.mkdir(parents=True, exist_ok=True)
        self._subscribers: List[Callable[[AuditLogRecord], None]] = []
        self._setup_logging()

    def _setup_logging(self) -> None:
        """Configure standard Python logger with rotating file handler."""
        self.logger = logging.getLogger("FirefoxManager")
        self.logger.setLevel(logging.DEBUG)

        if not self.logger.handlers:
            # File handler - 10MB per file, keeping 5 backups
            log_file = self.log_dir / "firefox_manager.log"
            file_handler = RotatingFileHandler(
                log_file, maxBytes=10 * 1024 * 1024, backupCount=5, encoding="utf-8"
            )
            file_formatter = logging.Formatter(
                "%(asctime)s [%(levelname)s] [%(name)s] %(message)s"
            )
            file_handler.setFormatter(file_formatter)
            file_handler.setLevel(logging.DEBUG)
            self.logger.addHandler(file_handler)

            # Console handler
            console_handler = logging.StreamHandler()
            console_formatter = logging.Formatter(
                "%(asctime)s [%(levelname)s] %(message)s"
            )
            console_handler.setFormatter(console_formatter)
            console_handler.setLevel(logging.INFO)
            self.logger.addHandler(console_handler)

    def subscribe(self, callback: Callable[[AuditLogRecord], None]) -> None:
        """Register a callback for real-time audit log streaming."""
        if callback not in self._subscribers:
            self._subscribers.append(callback)

    def unsubscribe(self, callback: Callable[[AuditLogRecord], None]) -> None:
        """Unregister callback."""
        if callback in self._subscribers:
            self._subscribers.remove(callback)

    def log(
        self,
        agent_name: str,
        action: str,
        target: Optional[str] = None,
        details: Optional[str] = None,
        severity: AuditSeverity = AuditSeverity.INFO,
    ) -> AuditLogRecord:
        """
        Record an audit log entry.
        Saves to SQLite audit_logs table, writes to rotating log file,
        and broadcasts to GUI subscribers.
        """
        record = AuditLogRecord(
            timestamp=datetime.now(timezone.utc).isoformat(),
            agent_name=agent_name,
            action=action,
            target=target,
            details=details,
            severity=severity,
        )

        # 1. Write to database
        try:
            db.add_audit_log(record)
        except Exception as e:
            self.logger.error(f"Failed to record audit log to database: {e}")

        # 2. Write to Python standard log
        msg = f"[{agent_name}] {action}"
        if target:
            msg += f" | Target: {target}"
        if details:
            msg += f" | Details: {details}"

        if severity == AuditSeverity.DEBUG:
            self.logger.debug(msg)
        elif severity == AuditSeverity.INFO:
            self.logger.info(msg)
        elif severity == AuditSeverity.WARNING:
            self.logger.warning(msg)
        elif severity == AuditSeverity.ERROR:
            self.logger.error(msg)
        elif severity == AuditSeverity.CRITICAL:
            self.logger.critical(msg)

        # 3. Broadcast to GUI subscribers
        for sub in list(self._subscribers):
            try:
                sub(record)
            except Exception:
                pass

        return record


# Global audit logger instance
audit_logger = AuditLogger()

