"""
Manual Authentication Coordinator.
Allows authorized users to complete authentication natively in the Firefox UI
without exposing credentials to automation or bypassing login screens.
"""

from typing import Optional
from datetime import datetime, timezone

from firefox_manager.database.database import db
from firefox_manager.database.models import AccountStatus, AuditSeverity
from firefox_manager.core.profile_manager import profile_manager
from firefox_manager.core.process_manager import process_manager
from firefox_manager.security.audit_logger import audit_logger


class ManualAuthenticationCoordinator:
    """Manages the interactive user login workflow inside Firefox."""

    def __init__(self):
        pass

    def start_manual_login(
        self, account_id: str, service_login_url: Optional[str] = None
    ) -> int:
        """
        Open the dedicated profile in Firefox directly at the service's login URL.
        Brings the window to front so user can enter credentials, complete 2FA, etc.
        """
        account = db.get_account(account_id)
        if not account:
            raise ValueError(f"Account '{account_id}' not found.")

        if not account.profile_id:
            raise ValueError(
                f"Account '{account.username}' is not associated with any Firefox profile."
            )

        profile = db.get_profile(account.profile_id)
        if not profile:
            raise ValueError(f"Associated profile '{account.profile_id}' not found.")

        target_url = service_login_url or f"https://www.{account.service_name}.com"

        # Launch profile or bring to front if already running
        if process_manager.is_running(profile.id):
            pid = process_manager.get_pid(profile.id)
            process_manager.bring_to_front(profile.id)
        else:
            pid = profile_manager.launch_profile(profile.id, initial_url=target_url)

        audit_logger.log(
            agent_name="ManualAuth",
            action="MANUAL_LOGIN_STARTED",
            target=account.username,
            details=f"Opened profile '{profile.name}' for user to sign into {account.service_name}",
        )
        return pid or 0

    def confirm_manual_login(self, account_id: str) -> None:
        """
        Invoked when the user has finished authenticating in Firefox.
        Marks account status as ACTIVE and updates timestamps.
        """
        account = db.get_account(account_id)
        if not account:
            raise ValueError(f"Account '{account_id}' not found.")

        now_iso = datetime.now(timezone.utc).isoformat()
        db.update_account_status(
            account_id=account_id,
            status=AccountStatus.ACTIVE,
            last_login_at=now_iso,
        )

        audit_logger.log(
            agent_name="ManualAuth",
            action="MANUAL_LOGIN_CONFIRMED",
            target=account.username,
            details=f"Account '{account.username}' marked as ACTIVE on {account.service_name}",
        )


# Global manual auth instance
manual_auth = ManualAuthenticationCoordinator()

