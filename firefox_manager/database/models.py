"""
Data models and schemas for Firefox Multi-Profile Manager.
Utilizes Pydantic for validation, serialization, and typing.
"""

from datetime import datetime, timezone
from enum import Enum
from typing import Optional, List
import uuid
from pydantic import BaseModel, Field


class ProfileStatus(str, Enum):
    """Lifecycle status of a Firefox profile."""
    STOPPED = "stopped"
    STARTING = "starting"
    RUNNING = "running"
    RESTARTING = "restarting"
    STOPPING = "stopping"
    ERROR = "error"
    RECOVERING = "recovering"


class AccountStatus(str, Enum):
    """Status of an authorized account."""
    ACTIVE = "active"
    REQUIRES_LOGIN = "requires_login"
    VERIFICATION_NEEDED = "verification_needed"
    SESSION_EXPIRED = "session_expired"
    LOCKED = "locked"
    UNKNOWN = "unknown"


class AuditSeverity(str, Enum):
    """Severity levels for audit logs."""
    DEBUG = "DEBUG"
    INFO = "INFO"
    WARNING = "WARNING"
    ERROR = "ERROR"
    CRITICAL = "CRITICAL"


class ProfileRecord(BaseModel):
    """Database entity representing a managed Firefox profile."""
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    name: str
    directory_name: str
    custom_user_agent: Optional[str] = None
    proxy_server: Optional[str] = None
    notes: Optional[str] = ""
    tags: str = ""  # Comma-separated tags
    is_active: bool = False
    status: ProfileStatus = ProfileStatus.STOPPED
    pid: Optional[int] = None
    created_at: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    last_launched_at: Optional[str] = None
    last_stopped_at: Optional[str] = None
    disk_usage_bytes: int = 0

    @property
    def tag_list(self) -> List[str]:
        if not self.tags:
            return []
        return [t.strip() for t in self.tags.split(",") if t.strip()]


class AccountRecord(BaseModel):
    """Database entity representing an authorized service account mapped to a profile."""
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    service_name: str
    username: str
    email: Optional[str] = None
    profile_id: Optional[str] = None
    status: AccountStatus = AccountStatus.REQUIRES_LOGIN
    created_at: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    last_login_at: Optional[str] = None
    session_expires_at: Optional[str] = None
    notes: Optional[str] = ""


class AuditLogRecord(BaseModel):
    """Structured audit trail record."""
    id: Optional[int] = None
    timestamp: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    agent_name: str
    action: str
    target: Optional[str] = None
    details: Optional[str] = None
    severity: AuditSeverity = AuditSeverity.INFO


class ProcessMetricRecord(BaseModel):
    """Resource snapshot for a running profile instance."""
    id: Optional[int] = None
    profile_id: str
    pid: int
    cpu_percent: float
    memory_mb: float
    recorded_at: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )

