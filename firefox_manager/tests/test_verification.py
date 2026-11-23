"""
Unit tests for Human-in-the-Loop Verification Handler.
Tests challenge interception, automation pausing, and resolution.
"""

import pytest
import threading
import time
from firefox_manager.authentication.verification_handler import VerificationHandler
from firefox_manager.database.models import AccountStatus


def test_verification_request_and_resolution(monkeypatch):
    vh = VerificationHandler()

    # Track callback invocation
    notified_requests = []
    vh.subscribe(lambda req: notified_requests.append(req))

    # Request human verification
    req = vh.request_human_verification(
        profile_id="prof-challenge-1",
        account_id=None,
        challenge_type="Cloudflare Turnstile",
        details="User must complete challenge in Firefox window",
    )

    assert req.request_id in [r.request_id for r in vh.get_pending_requests()]
    assert len(notified_requests) == 1
    assert notified_requests[0].challenge_type == "Cloudflare Turnstile"
    assert not req.resolved

    # Simulate background automation thread awaiting user completion
    resolved_event = threading.Event()

    def background_worker():
        ok = req.wait_for_resolution(timeout=5.0)
        if ok and req.success:
            resolved_event.set()

    thread = threading.Thread(target=background_worker)
    thread.start()

    # User completes verification in GUI
    time.sleep(0.1)
    vh.resolve_verification(req.request_id, success=True)

    thread.join(timeout=2.0)
    assert resolved_event.is_set()
    assert len(vh.get_pending_requests()) == 0

