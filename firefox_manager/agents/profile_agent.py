"""
Agent 1: Profile Agent.
Manages Firefox profile creation, launching, termination, and lifecycle.
Communicates status changes and operations through the central orchestrator.
"""

from typing import Optional, List, Dict, Any
from firefox_manager.core.profile_manager import profile_manager
from firefox_manager.database.database import db
from firefox_manager.database.models import ProfileRecord, ProfileStatus
from firefox_manager.security.audit_logger import audit_logger


class ProfileAgent:
    """Agent responsible for profile management and lifecycle operations."""

    name = "ProfileAgent"

    def __init__(self, orchestrator=None):
        self.orchestrator = orchestrator

    def create_profile(
        self,
        name: str,
        custom_user_agent: Optional[str] = None,
        proxy_server: Optional[str] = None,
        notes: Optional[str] = "",
        tags: Optional[str] = "",
    ) -> ProfileRecord:
        """Create a new independent profile."""
        profile = profile_manager.create_profile(
            name=name,
            custom_user_agent=custom_user_agent,
            proxy_server=proxy_server,
            notes=notes,
            tags=tags,
        )
        if self.orchestrator:
            self.orchestrator.notify_event("PROFILE_CREATED", {"profile_id": profile.id, "name": profile.name})
        return profile

    def launch_profile(self, profile_id: str, initial_url: Optional[str] = None) -> int:
        """Launch an individual profile natively."""
        pid = profile_manager.launch_profile(profile_id, initial_url)
        if self.orchestrator:
            self.orchestrator.notify_event("PROFILE_LAUNCHED", {"profile_id": profile_id, "pid": pid})
        return pid

    def stop_profile(self, profile_id: str) -> bool:
        """Close an individual profile."""
        success = profile_manager.stop_profile(profile_id)
        if self.orchestrator:
            self.orchestrator.notify_event("PROFILE_STOPPED", {"profile_id": profile_id})
        return success

    def restart_profile(self, profile_id: str, initial_url: Optional[str] = None) -> int:
        """Restart an individual profile."""
        pid = profile_manager.restart_profile(profile_id, initial_url)
        if self.orchestrator:
            self.orchestrator.notify_event("PROFILE_RESTARTED", {"profile_id": profile_id, "pid": pid})
        return pid

    def delete_profile(self, profile_id: str, remove_disk_files: bool = True) -> bool:
        """Delete an individual profile."""
        success = profile_manager.delete_profile(profile_id, remove_disk_files)
        if self.orchestrator:
            self.orchestrator.notify_event("PROFILE_DELETED", {"profile_id": profile_id})
        return success

    def list_profiles(self) -> List[ProfileRecord]:
        """Query all managed profiles."""
        return db.list_profiles()

    def get_profile(self, profile_id: str) -> Optional[ProfileRecord]:
        """Get profile by ID."""
        return db.get_profile(profile_id)

