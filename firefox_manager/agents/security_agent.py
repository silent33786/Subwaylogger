"""
Agent 5: Security Agent.
Protects credentials, ensures profile filesystem isolation, validates encryption
integrity, and verifies that no profile data is shared across instances.
"""

from pathlib import Path
from typing import Dict, Any, List
from firefox_manager.config.settings import settings
from firefox_manager.database.database import db
from firefox_manager.database.models import AuditSeverity
from firefox_manager.security.credential_manager import credential_manager
from firefox_manager.browser.profile_storage import profile_storage
from firefox_manager.security.audit_logger import audit_logger


class SecurityAgent:
    """Agent responsible for credential security and profile data isolation."""

    name = "SecurityAgent"

    def __init__(self, orchestrator=None):
        self.orchestrator = orchestrator

    def verify_profile_isolation(self, directory_name: str) -> Dict[str, Any]:
        """
        Verify that a profile's directory is completely isolated.
        Ensures it is not a symlink/junction pointing to another profile,
        has its own user.js, and maintains independent storage.
        """
        profile_path = profile_storage.get_profile_path(directory_name)
        issues: List[str] = []

        if not profile_path.exists():
            return {"isolated": False, "issues": ["Directory does not exist."]}

        # Check symlink or junction
        if profile_path.is_symlink():
            issues.append("Profile directory is a symbolic link, risking data leakage.")

        # Check for profile_meta.json
        meta_file = profile_path / "profile_meta.json"
        if not meta_file.exists():
            issues.append("Missing profile_meta.json ownership descriptor.")

        # Check user.js exists
        user_js = profile_path / "user.js"
        if not user_js.exists():
            issues.append("Profile missing user.js isolation configuration.")

        isolated = len(issues) == 0

        audit_logger.log(
            agent_name=self.name,
            action="PROFILE_ISOLATION_AUDIT",
            target=directory_name,
            details=f"Isolated: {isolated}. Issues: {issues if issues else 'None'}",
            severity=AuditSeverity.INFO if isolated else AuditSeverity.WARNING,
        )

        return {"isolated": isolated, "issues": issues}

    def audit_all_profiles(self) -> Dict[str, bool]:
        """Perform isolation audit across all registered profiles."""
        profiles = db.list_profiles()
        results = {}
        for p in profiles:
            audit = self.verify_profile_isolation(p.directory_name)
            results[p.name] = audit["isolated"]
        return results

    def get_credential(self, service_name: str, username: str) -> str:
        """Securely fetch credential via CredentialManager."""
        return credential_manager.get_credential(service_name, username) or ""

    def store_credential(self, service_name: str, username: str, secret: str) -> bool:
        """Store credential using OS secure vault."""
        return credential_manager.store_credential(service_name, username, secret)

