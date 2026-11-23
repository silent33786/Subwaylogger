"""
Human-in-the-Loop Security Verification Handler.
Strictly adheres to security and ethical automation standards:
PAUSES automation, BRINGS Firefox window to front, NOTIFIES user via GUI,
and WAITS for human completion.
NEVER bypasses, solves, or defeats CAPTCHAs or security challenges.
"""

import threading
import uuid
from typing import Dict, Optional, Callable, List
from datetime import datetime, timezone

from firefox_manager.database.database import db
from firefox_manager.database.models import AccountStatus, AuditSeverity
from firefox_manager.core.process_manager import process_manager
from firefox_manager.security.audit_logger import audit_logger


class VerificationRequest:
    """Descriptor of a pending human verification request."""
    def __init__(
        self,
        request_id: str,
        profile_id: str,
        account_id: Optional[str],
        challenge_type: str,
        details: str,
        created_at: str,
    ):
        self.request_id = request_id
        self.profile_id = profile_id
        self.account_id = account_id
        self.challenge_type = challenge_type  # e.g., "CAPTCHA", "2FA", "Cloudflare Turnstile", "OTP"
        self.details = details
        self.created_at = created_at
        self.resolved = False
        self.success = False
        self._event = threading.Event()

    def wait_for_resolution(self, timeout: Optional[float] = None) -> bool:
        """Block caller thread until user manually completes verification."""
        return self._event.wait(timeout=timeout)

    def resolve(self, success: bool) -> None:
        """Called when user confirms manual completion in GUI."""
        self.resolved = True
        self.success = success
        self._event.set()


class VerificationHandler:
    """Manages human-in-the-loop verification workflow."""

    def __init__(self):
        self._pending_requests: Dict[str, VerificationRequest] = {}
        self._lock = threading.RLock()
        self._listeners: List[Callable[[VerificationRequest], None]] = []

    def subscribe(self, callback: Callable[[VerificationRequest], None]) -> None:
        """Register listener for new verification requests (e.g. GUI notification)."""
        if callback not in self._listeners:
            self._listeners.append(callback)

    def request_human_verification(
        self,
        profile_id: str,
        account_id: Optional[str] = None,
        challenge_type: str = "CAPTCHA / Security Challenge",
        details: str = "Please solve the security challenge in the opened Firefox window.",
    ) -> VerificationRequest:
        """
        Pause automation and request human intervention.
        1. Updates account status to VERIFICATION_NEEDED.
        2. Focuses and restores Firefox window to front.
        3. Emits alert event to dashboard.
        4. Returns request handle so caller can await completion.
        """
        request_id = str(uuid.uuid4())
        req = VerificationRequest(
            request_id=request_id,
            profile_id=profile_id,
            account_id=account_id,
            challenge_type=challenge_type,
            details=details,
            created_at=datetime.now(timezone.utc).isoformat(),
        )

        with self._lock:
            self._pending_requests[request_id] = req

        # 1. Update account status if bound
        if account_id:
            db.update_account_status(account_id, AccountStatus.VERIFICATION_NEEDED)

        # 2. Bring Firefox window to the foreground
        process_manager.bring_to_front(profile_id)

        # 3. Log audit event
        audit_logger.log(
            agent_name="VerificationHandler",
            action="SECURITY_CHALLENGE_DETECTED",
            target=profile_id,
            details=f"Paused automation. Challenge type: '{challenge_type}'. Awaiting human input.",
            severity=AuditSeverity.WARNING,
        )

        # 4. Notify GUI listeners
        for listener in list(self._listeners):
            try:
                listener(req)
            except Exception:
                pass

        return req

    def resolve_verification(self, request_id: str, success: bool = True) -> bool:
        """
        Mark a verification challenge as completed by the authorized user.
        Resumes any waiting automation threads.
        """
        with self._lock:
            req = self._pending_requests.get(request_id)
            if not req:
                return False

            req.resolve(success=success)
            del self._pending_requests[request_id]

            if req.account_id:
                new_status = AccountStatus.ACTIVE if success else AccountStatus.REQUIRES_LOGIN
                db.update_account_status(req.account_id, new_status)

            audit_logger.log(
                agent_name="VerificationHandler",
                action="SECURITY_CHALLENGE_RESOLVED",
                target=req.profile_id,
                details=f"Human verification outcome: {'Success' if success else 'Failed/Cancelled'}",
                severity=AuditSeverity.INFO if success else AuditSeverity.WARNING,
            )
            return True

    def get_pending_requests(self) -> List[VerificationRequest]:
        """Return list of all currently unresolved challenges."""
        with self._lock:
            return list(self._pending_requests.values())


# Global verification handler
verification_handler = VerificationHandler()

