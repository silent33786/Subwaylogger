"""
SQLite Database engine for Firefox Multi-Profile Manager.
Provides thread-safe persistence, WAL mode, transaction isolation, and automated backups.
"""

import sqlite3
import threading
from pathlib import Path
from typing import List, Optional, Dict, Any
from datetime import datetime, timezone
import shutil

from firefox_manager.config.settings import settings
from firefox_manager.database.models import (
    ProfileRecord,
    AccountRecord,
    AuditLogRecord,
    ProcessMetricRecord,
    ProfileStatus,
    AccountStatus,
    AuditSeverity,
)


class Database:
    """Enterprise SQLite Database manager."""

    def __init__(self, db_path: Optional[Path] = None):
        self.db_path = Path(db_path or settings.db_path).resolve()
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self._init_schema()

    def _get_connection(self) -> sqlite3.Connection:
        """Create an optimized SQLite connection."""
        conn = sqlite3.connect(
            str(self.db_path),
            timeout=30.0,
            check_same_thread=False
        )
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode = WAL;")
        conn.execute("PRAGMA synchronous = NORMAL;")
        conn.execute("PRAGMA foreign_keys = ON;")
        return conn

    def _init_schema(self) -> None:
        """Initialize database tables, indexes, and constraints."""
        with self._lock, self._get_connection() as conn:
            cursor = conn.cursor()

            # Profiles table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS profiles (
                    id TEXT PRIMARY KEY,
                    name TEXT UNIQUE NOT NULL,
                    directory_name TEXT UNIQUE NOT NULL,
                    custom_user_agent TEXT,
                    proxy_server TEXT,
                    notes TEXT,
                    tags TEXT DEFAULT '',
                    is_active INTEGER DEFAULT 0,
                    status TEXT DEFAULT 'stopped',
                    pid INTEGER,
                    created_at TEXT NOT NULL,
                    last_launched_at TEXT,
                    last_stopped_at TEXT,
                    disk_usage_bytes INTEGER DEFAULT 0
                )
            """)

            # Accounts table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS accounts (
                    id TEXT PRIMARY KEY,
                    service_name TEXT NOT NULL,
                    username TEXT NOT NULL,
                    email TEXT,
                    profile_id TEXT,
                    status TEXT DEFAULT 'requires_login',
                    created_at TEXT NOT NULL,
                    last_login_at TEXT,
                    session_expires_at TEXT,
                    notes TEXT,
                    FOREIGN KEY (profile_id) REFERENCES profiles(id) ON DELETE SET NULL,
                    UNIQUE(service_name, username)
                )
            """)

            # Audit Logs table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS audit_logs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT NOT NULL,
                    agent_name TEXT NOT NULL,
                    action TEXT NOT NULL,
                    target TEXT,
                    details TEXT,
                    severity TEXT DEFAULT 'INFO'
                )
            """)

            # Process Metrics table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS process_metrics (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    profile_id TEXT NOT NULL,
                    pid INTEGER NOT NULL,
                    cpu_percent REAL DEFAULT 0.0,
                    memory_mb REAL DEFAULT 0.0,
                    recorded_at TEXT NOT NULL,
                    FOREIGN KEY (profile_id) REFERENCES profiles(id) ON DELETE CASCADE
                )
            """)

            # Indexes for high performance querying
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_profiles_status ON profiles(status);")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_accounts_profile ON accounts(profile_id);")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_audit_timestamp ON audit_logs(timestamp);")
            conn.commit()

    # =========================================================================
    # Profile Operations
    # =========================================================================

    def create_profile(self, profile: ProfileRecord) -> ProfileRecord:
        """Insert a new profile record."""
        with self._lock, self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT INTO profiles (
                    id, name, directory_name, custom_user_agent, proxy_server,
                    notes, tags, is_active, status, pid, created_at,
                    last_launched_at, last_stopped_at, disk_usage_bytes
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    profile.id,
                    profile.name,
                    profile.directory_name,
                    profile.custom_user_agent,
                    profile.proxy_server,
                    profile.notes,
                    profile.tags,
                    1 if profile.is_active else 0,
                    profile.status.value,
                    profile.pid,
                    profile.created_at,
                    profile.last_launched_at,
                    profile.last_stopped_at,
                    profile.disk_usage_bytes,
                ),
            )
            conn.commit()
            return profile

    def get_profile(self, profile_id: str) -> Optional[ProfileRecord]:
        """Fetch profile by ID."""
        with self._lock, self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM profiles WHERE id = ?", (profile_id,))
            row = cursor.fetchone()
            if row:
                data = dict(row)
                data["is_active"] = bool(data["is_active"])
                data["status"] = ProfileStatus(data["status"])
                return ProfileRecord(**data)
            return None

    def get_profile_by_name(self, name: str) -> Optional[ProfileRecord]:
        """Fetch profile by exact name."""
        with self._lock, self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM profiles WHERE name = ?", (name,))
            row = cursor.fetchone()
            if row:
                data = dict(row)
                data["is_active"] = bool(data["is_active"])
                data["status"] = ProfileStatus(data["status"])
                return ProfileRecord(**data)
            return None

    def list_profiles(self) -> List[ProfileRecord]:
        """Return all managed profiles ordered by name."""
        with self._lock, self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM profiles ORDER BY name ASC")
            results = []
            for row in cursor.fetchall():
                data = dict(row)
                data["is_active"] = bool(data["is_active"])
                data["status"] = ProfileStatus(data["status"])
                results.append(ProfileRecord(**data))
            return results

    def update_profile(self, profile: ProfileRecord) -> None:
        """Update an existing profile record."""
        with self._lock, self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                UPDATE profiles SET
                    name = ?,
                    directory_name = ?,
                    custom_user_agent = ?,
                    proxy_server = ?,
                    notes = ?,
                    tags = ?,
                    is_active = ?,
                    status = ?,
                    pid = ?,
                    last_launched_at = ?,
                    last_stopped_at = ?,
                    disk_usage_bytes = ?
                WHERE id = ?
                """,
                (
                    profile.name,
                    profile.directory_name,
                    profile.custom_user_agent,
                    profile.proxy_server,
                    profile.notes,
                    profile.tags,
                    1 if profile.is_active else 0,
                    profile.status.value,
                    profile.pid,
                    profile.last_launched_at,
                    profile.last_stopped_at,
                    profile.disk_usage_bytes,
                    profile.id,
                ),
            )
            conn.commit()

    def update_profile_status(
        self,
        profile_id: str,
        status: ProfileStatus,
        is_active: bool,
        pid: Optional[int] = None,
        last_launched_at: Optional[str] = None,
        last_stopped_at: Optional[str] = None,
    ) -> None:
        """Atomic update of profile status flags and process ID."""
        with self._lock, self._get_connection() as conn:
            cursor = conn.cursor()
            query = "UPDATE profiles SET status = ?, is_active = ?, pid = ?"
            params: List[Any] = [status.value, 1 if is_active else 0, pid]
            
            if last_launched_at is not None:
                query += ", last_launched_at = ?"
                params.append(last_launched_at)
            if last_stopped_at is not None:
                query += ", last_stopped_at = ?"
                params.append(last_stopped_at)
                
            query += " WHERE id = ?"
            params.append(profile_id)
            cursor.execute(query, params)
            conn.commit()

    def delete_profile(self, profile_id: str) -> bool:
        """Remove profile record from database."""
        with self._lock, self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM profiles WHERE id = ?", (profile_id,))
            conn.commit()
            return cursor.rowcount > 0

    # =========================================================================
    # Account Operations
    # =========================================================================

    def create_account(self, account: AccountRecord) -> AccountRecord:
        """Register a new authorized service account."""
        with self._lock, self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT INTO accounts (
                    id, service_name, username, email, profile_id,
                    status, created_at, last_login_at, session_expires_at, notes
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    account.id,
                    account.service_name,
                    account.username,
                    account.email,
                    account.profile_id,
                    account.status.value,
                    account.created_at,
                    account.last_login_at,
                    account.session_expires_at,
                    account.notes,
                ),
            )
            conn.commit()
            return account

    def get_account(self, account_id: str) -> Optional[AccountRecord]:
        """Fetch account by ID."""
        with self._lock, self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM accounts WHERE id = ?", (account_id,))
            row = cursor.fetchone()
            if row:
                data = dict(row)
                data["status"] = AccountStatus(data["status"])
                return AccountRecord(**data)
            return None

    def list_accounts(self) -> List[AccountRecord]:
        """Return all accounts."""
        with self._lock, self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM accounts ORDER BY service_name, username ASC")
            results = []
            for row in cursor.fetchall():
                data = dict(row)
                data["status"] = AccountStatus(data["status"])
                results.append(AccountRecord(**data))
            return results

    def get_accounts_for_profile(self, profile_id: str) -> List[AccountRecord]:
        """Return accounts associated with a specific profile."""
        with self._lock, self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM accounts WHERE profile_id = ?", (profile_id,))
            results = []
            for row in cursor.fetchall():
                data = dict(row)
                data["status"] = AccountStatus(data["status"])
                results.append(AccountRecord(**data))
            return results

    def update_account(self, account: AccountRecord) -> None:
        """Update account record."""
        with self._lock, self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                UPDATE accounts SET
                    service_name = ?,
                    username = ?,
                    email = ?,
                    profile_id = ?,
                    status = ?,
                    last_login_at = ?,
                    session_expires_at = ?,
                    notes = ?
                WHERE id = ?
                """,
                (
                    account.service_name,
                    account.username,
                    account.email,
                    account.profile_id,
                    account.status.value,
                    account.last_login_at,
                    account.session_expires_at,
                    account.notes,
                    account.id,
                ),
            )
            conn.commit()

    def update_account_status(
        self,
        account_id: str,
        status: AccountStatus,
        last_login_at: Optional[str] = None
    ) -> None:
        """Update account status and optional login timestamp."""
        with self._lock, self._get_connection() as conn:
            cursor = conn.cursor()
            if last_login_at:
                cursor.execute(
                    "UPDATE accounts SET status = ?, last_login_at = ? WHERE id = ?",
                    (status.value, last_login_at, account_id),
                )
            else:
                cursor.execute(
                    "UPDATE accounts SET status = ? WHERE id = ?",
                    (status.value, account_id),
                )
            conn.commit()

    def delete_account(self, account_id: str) -> bool:
        """Remove account record."""
        with self._lock, self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM accounts WHERE id = ?", (account_id,))
            conn.commit()
            return cursor.rowcount > 0

    # =========================================================================
    # Audit Logs Operations
    # =========================================================================

    def add_audit_log(self, record: AuditLogRecord) -> AuditLogRecord:
        """Insert an audit log entry."""
        with self._lock, self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT INTO audit_logs (timestamp, agent_name, action, target, details, severity)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    record.timestamp,
                    record.agent_name,
                    record.action,
                    record.target,
                    record.details,
                    record.severity.value,
                ),
            )
            conn.commit()
            record.id = cursor.lastrowid
            return record

    def get_recent_audit_logs(self, limit: int = 100) -> List[AuditLogRecord]:
        """Fetch latest audit logs in reverse chronological order."""
        with self._lock, self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT * FROM audit_logs ORDER BY id DESC LIMIT ?", (limit,)
            )
            results = []
            for row in cursor.fetchall():
                data = dict(row)
                data["severity"] = AuditSeverity(data["severity"])
                results.append(AuditLogRecord(**data))
            return results

    # =========================================================================
    # Process Metrics Operations
    # =========================================================================

    def record_process_metric(self, metric: ProcessMetricRecord) -> None:
        """Record real-time CPU and memory usage."""
        with self._lock, self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT INTO process_metrics (profile_id, pid, cpu_percent, memory_mb, recorded_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                (
                    metric.profile_id,
                    metric.pid,
                    metric.cpu_percent,
                    metric.memory_mb,
                    metric.recorded_at,
                ),
            )
            conn.commit()

    # =========================================================================
    # Reliability & Backup Operations
    # =========================================================================

    def backup_database(self, destination_dir: Optional[Path] = None) -> Path:
        """Create a safe point-in-time SQLite backup using sqlite3 backup API."""
        dest_dir = Path(destination_dir or settings.backups_dir)
        dest_dir.mkdir(parents=True, exist_ok=True)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
        backup_file = dest_dir / f"backup_firefox_manager_{timestamp}.db"

        with self._lock:
            source_conn = self._get_connection()
            try:
                dest_conn = sqlite3.connect(str(backup_file))
                try:
                    source_conn.backup(dest_conn)
                finally:
                    dest_conn.close()
            finally:
                source_conn.close()

        # Enforce retention policy
        self._prune_backups(dest_dir, settings.backup_retention_count)
        return backup_file

    def _prune_backups(self, dest_dir: Path, keep: int) -> None:
        """Delete oldest backups if count exceeds retention limit."""
        backups = sorted(dest_dir.glob("backup_firefox_manager_*.db"), key=lambda p: p.stat().st_mtime)
        while len(backups) > keep:
            oldest = backups.pop(0)
            try:
                oldest.unlink(missing_ok=True)
            except OSError:
                pass


# Global database instance
db = Database()
