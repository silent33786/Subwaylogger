"""
Agent 3: Account Agent.
Maintains authorized service accounts, links accounts to dedicated Firefox profiles,
tracks authentication statuses, and coordinates manual user authentication.
"""

from typing import Optional, List
from firefox_manager.database.database import db
from firefox_manager.database.models import AccountRecord, AccountStatus, AuditSeverity
from firefox_manager.security.credential_manager import credential_manager
from firefox_manager.security.audit_logger import audit_logger
from firefox_manager.authentication.manual_auth import manual_auth


class AccountAgent:
    """Agent managing authorized accounts and profile associations."""

    name = "AccountAgent"

    def __init__(self, orchestrator=None):
        self.orchestrator = orchestrator

    def add_account(
        self,
        service_name: str,
        username: str,
        email: Optional[str] = None,
        profile_id: Optional[str] = None,
        password: Optional[str] = None,
        notes: Optional[str] = "",
    ) -> AccountRecord:
        """
        Register a new account.
        If a password is provided, securely store it via CredentialManager (never in plaintext DB).
        """
        # Validate profile exists if supplied
        if profile_id:
            profile = db.get_profile(profile_id)
            if not profile:
                raise ValueError(f"Profile '{profile_id}' not found.")

        account = AccountRecord(
            service_name=service_name.strip(),
            username=username.strip(),
            email=email.strip() if email else None,
            profile_id=profile_id,
            status=AccountStatus.REQUIRES_LOGIN,
            notes=notes or "",
        )

        created = db.create_account(account)

        # Store password in secure OS vault if supplied
        if password:
            credential_manager.store_credential(
                service_name=account.service_name,
                username=account.username,
                secret=password,
            )

        audit_logger.log(
            agent_name=self.name,
            action="ACCOUNT_ADDED",
            target=account.username,
            details=f"Service: {account.service_name}, Profile: {profile_id or 'None'}",
        )

        if self.orchestrator:
            self.orchestrator.notify_event("ACCOUNT_ADDED", {"account_id": created.id})

        return created

    def link_account_to_profile(self, account_id: str, profile_id: Optional[str]) -> None:
        """Associate or disassociate an account with a Firefox profile."""
        account = db.get_account(account_id)
        if not account:
            raise ValueError(f"Account '{account_id}' not found.")

        if profile_id:
            profile = db.get_profile(profile_id)
            if not profile:
                raise ValueError(f"Profile '{profile_id}' not found.")

        account.profile_id = profile_id
        db.update_account(account)

        audit_logger.log(
            agent_name=self.name,
            action="ACCOUNT_PROFILE_LINKED",
            target=account.username,
            details=f"Linked to profile {profile_id or 'Unlinked'}",
        )

        if self.orchestrator:
            self.orchestrator.notify_event("ACCOUNT_UPDATED", {"account_id": account_id})

    def delete_account(self, account_id: str) -> bool:
        """Remove account and erase any securely stored credentials."""
        account = db.get_account(account_id)
        if not account:
            return False

        # Clear credentials from vault
        credential_manager.delete_credential(account.service_name, account.username)

        deleted = db.delete_account(account_id)

        audit_logger.log(
            agent_name=self.name,
            action="ACCOUNT_DELETED",
            target=account.username,
            details=f"Deleted account from service {account.service_name}",
        )

        if self.orchestrator:
            self.orchestrator.notify_event("ACCOUNT_DELETED", {"account_id": account_id})

        return deleted

    def launch_for_manual_auth(self, account_id: str, login_url: Optional[str] = None) -> int:
        """Launch Firefox for the user to manually sign in."""
        return manual_auth.start_manual_login(account_id, login_url)

    def confirm_manual_auth(self, account_id: str) -> None:
        """Confirm that the user completed authentication in the browser."""
        manual_auth.confirm_manual_login(account_id)
        if self.orchestrator:
            self.orchestrator.notify_event("ACCOUNT_STATUS_CHANGED", {"account_id": account_id})

    def list_accounts(self) -> List[AccountRecord]:
        """Fetch all registered accounts."""
        return db.list_accounts()

    def get_account(self, account_id: str) -> Optional[AccountRecord]:
        """Fetch account by ID."""
        return db.get_account(account_id)

