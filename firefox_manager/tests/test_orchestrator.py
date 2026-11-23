"""
Integration tests for Orchestrator and Agent coordination.
"""

import pytest
import tempfile
from pathlib import Path
from firefox_manager.core.orchestrator import Orchestrator


@pytest.fixture
def temp_orchestrator(monkeypatch):
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmpdir:
        base = Path(tmpdir)
        monkeypatch.setattr("firefox_manager.config.settings.settings.data_dir", base / "data")
        monkeypatch.setattr("firefox_manager.config.settings.settings.profiles_dir", base / "profiles")
        monkeypatch.setattr("firefox_manager.config.settings.settings.logs_dir", base / "logs")
        monkeypatch.setattr("firefox_manager.config.settings.settings.backups_dir", base / "backups")

        from firefox_manager.database.database import Database
        isolated_db = Database(db_path=base / "data" / "isolated.db")
        monkeypatch.setattr("firefox_manager.core.orchestrator.db", isolated_db)
        monkeypatch.setattr("firefox_manager.agents.profile_agent.db", isolated_db)

        orch = Orchestrator()
        orch.initialize()
        yield orch
        orch.shutdown()


def test_orchestrator_initialization_and_summary(temp_orchestrator):
    summary = temp_orchestrator.get_dashboard_summary()
    assert "total_profiles" in summary
    assert "active_profiles" in summary
    assert "connected_accounts" in summary
    assert summary["total_profiles"] == 0


def test_event_broadcasting(temp_orchestrator):
    events_received = []

    def on_event(name, payload):
        events_received.append((name, payload))

    temp_orchestrator.subscribe_event("TEST_EVENT", on_event)
    temp_orchestrator.notify_event("TEST_EVENT", {"status": "ok"})

    assert len(events_received) == 1
    assert events_received[0][0] == "TEST_EVENT"
    assert events_received[0][1] == {"status": "ok"}
