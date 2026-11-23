"""
Session Manager and Session Persistence Engine.
Monitors persistent cookies and session states in Firefox profile directories.
Detects expired sessions and flags accounts that require manual re-authentication.
"""

import sqlite3
import time
from pathlib import Path
from typing import Optional, List, Dict, Any
from datetime import datetime, timezone

from firefox_manager.config.settings import settings
from firefox_manager.database.database import db
from firefox_manager.database.models import AccountRecord, AccountStatus, AuditSeverity
from firefox_manager.browser.profile_storage import profile_storage
from firefox_manager.security.audit_logger import audit_logger


class SessionManager:
    """Enterprise persistent session validator and monitor."""

    def __init__(self):
        pass

    def inspect_profile_cookies(self, directory_name: str) -> Dict[str, Any]:
        """
        Safely inspect cookies.sqlite in read-only mode to verify session persistence.
        Does not disrupt running Firefox instances.
        """
        profile_path = profile_storage.get_profile_path(directory_name)
        cookies_db = profile_path / "cookies.sqlite"

        if not cookies_db.exists():
            return {
                "has_cookies": False,
                "total_cookies": 0,
                "domains": [],
                "latest_expiry": None,
            }

        try:
            # Open SQLite in URI read-only immutable mode
            uri_path = f"file:{cookies_db.as_posix()}?mode=ro&immutable=1"
            conn = sqlite3.connect(uri_path, uri=True, timeout=5.0)
            cursor = conn.cursor()

            # Query count and unique host domains
            cursor.execute("SELECT count(*), max(expiry) FROM moz_cookies")
            count, max_expiry = cursor.fetchone()

            cursor.execute("SELECT DISTINCT host FROM moz_cookies LIMIT 50")
            domains = [row[0] for row in cursor.fetchall()]
            conn.close()

            return {
                "has_cookies": count > 0,
                "total_cookies": count or 0,
                "domains": domains,
                "latest_expiry": max_expiry,
            }
        except Exception as e:
            audit_logger.log(
                agent_name="SessionManager",
                action="COOKIE_INSPECT_WARNING",
                target=directory_name,
                details=f"Could not read cookies.sqlite: {e}",
                severity=AuditSeverity.DEBUG,
            )
            return {
                "has_cookies": False,
                "total_cookies": 0,
                "domains": [],
                "latest_expiry": None,
            }

    def evaluate_account_sessions(self) -> List[AccountRecord]:
        """
        Scan all registered accounts and verify session validity.
        Flags expired accounts as SESSION_EXPIRED.
        """
        expired_accounts = []
        accounts = db.list_accounts()
        now_ts = datetime.now(timezone.utc).timestamp()

        for account in accounts:
            if not account.profile_id:
                continue

            profile = db.get_profile(account.profile_id)
            if not profile:
                continue

            # 1. Check if session expiration timestamp has elapsed
            if account.session_expires_at:
                try:
                    exp_dt = datetime.fromisoformat(account.session_expires_at)
                    if exp_dt.timestamp() < now_ts:
                        if account.status != AccountStatus.SESSION_EXPIRED:
                            db.update_account_status(account.id, AccountStatus.SESSION_EXPIRED)
                            account.status = AccountStatus.SESSION_EXPIRED
                            expired_accounts.append(account)
                            audit_logger.log(
                                agent_name="SessionManager",
                                action="SESSION_EXPIRED",
                                target=account.username,
                                details=f"Session expired for {account.service_name} on profile {profile.name}",
                                severity=AuditSeverity.WARNING,
                            )
                        continue
                except ValueError:
                    pass

            # 2. Check if cookies exist for profile
            cookie_info = self.inspect_profile_cookies(profile.directory_name)
            if not cookie_info["has_cookies"] and account.status == AccountStatus.ACTIVE:
                # Active account but zero cookies in profile
                db.update_account_status(account.id, AccountStatus.REQUIRES_LOGIN)
                account.status = AccountStatus.REQUIRES_LOGIN
                expired_accounts.append(account)
                audit_logger.log(
                    agent_name="SessionManager",
                    action="SESSION_MISSING_COOKIES",
                    target=account.username,
                    details=f"No cookies found for active account {account.username} on {profile.name}",
                    severity=AuditSeverity.INFO,
                )

        return expired_accounts

    def mark_session_authenticated(
        self, account_id: str, expiry_seconds: Optional[int] = None
    ) -> None:
        """Mark an account as successfully authenticated with active session."""
        now_iso = datetime.now(timezone.utc).isoformat()
        expires_iso = None
        if expiry_seconds:
            expires_iso = datetime.fromtimestamp(
                time.time() + expiry_seconds, timezone.utc
            ).isoformat()

        account = db.get_account(account_id)
        if account:
            account.status = AccountStatus.ACTIVE
            account.last_login_at = now_iso
            account.session_expires_at = expires_iso
            db.update_account(account)

            audit_logger.log(
                agent_name="SessionManager",
                action="SESSION_AUTHENTICATED",
                target=account.username,
                details=f"Account {account.username} authenticated on service {account.service_name}",
            )


# Global session manager
session_manager = SessionManager()

