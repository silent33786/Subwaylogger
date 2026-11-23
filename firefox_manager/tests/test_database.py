"""
Unit tests for Database engine and schemas.
"""

import pytest
import tempfile
from pathlib import Path

from firefox_manager.database.database import Database
from firefox_manager.database.models import (
    ProfileRecord,
    AccountRecord,
    AuditLogRecord,
    ProfileStatus,
    AccountStatus,
    AuditSeverity,
)


@pytest.fixture
def temp_db():
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmpdir:
        db_path = Path(tmpdir) / "test.db"
        test_db = Database(db_path=db_path)
        yield test_db


def test_profile_crud(temp_db):
    profile = ProfileRecord(
        id="test-p1",
        name="Test Profile 1",
        directory_name="test_p1_dir",
        tags="alpha, beta",
    )
    temp_db.create_profile(profile)

    fetched = temp_db.get_profile("test-p1")
    assert fetched is not None
    assert fetched.name == "Test Profile 1"
    assert fetched.status == ProfileStatus.STOPPED
    assert fetched.tag_list == ["alpha", "beta"]

    # Update status
    temp_db.update_profile_status("test-p1", ProfileStatus.RUNNING, is_active=True, pid=1234)
    updated = temp_db.get_profile("test-p1")
    assert updated.status == ProfileStatus.RUNNING
    assert updated.is_active is True
    assert updated.pid == 1234

    # List
    all_profiles = temp_db.list_profiles()
    assert len(all_profiles) == 1

    # Delete
    deleted = temp_db.delete_profile("test-p1")
    assert deleted is True
    assert temp_db.get_profile("test-p1") is None


def test_account_crud(temp_db):
    profile = ProfileRecord(
        id="profile-acct",
        name="Profile For Account",
        directory_name="profile_acct_dir",
    )
    temp_db.create_profile(profile)

    account = AccountRecord(
        id="acct-1",
        service_name="GitHub",
        username="octocat",
        email="octo@github.com",
        profile_id="profile-acct",
    )
    temp_db.create_account(account)

    fetched = temp_db.get_account("acct-1")
    assert fetched is not None
    assert fetched.service_name == "GitHub"
    assert fetched.profile_id == "profile-acct"
    assert fetched.status == AccountStatus.REQUIRES_LOGIN

    # Update status
    temp_db.update_account_status("acct-1", AccountStatus.ACTIVE, last_login_at="2026-11-04T00:00:00Z")
    updated = temp_db.get_account("acct-1")
    assert updated.status == AccountStatus.ACTIVE
    assert updated.last_login_at == "2026-11-04T00:00:00Z"

    # Profile lookup
    accounts_for_p = temp_db.get_accounts_for_profile("profile-acct")
    assert len(accounts_for_p) == 1
    assert accounts_for_p[0].username == "octocat"


def test_audit_logs(temp_db):
    log = AuditLogRecord(
        agent_name="TestAgent",
        action="TEST_ACTION",
        target="Target1",
        details="Sample details",
        severity=AuditSeverity.INFO,
    )
    temp_db.add_audit_log(log)

    recent = temp_db.get_recent_audit_logs(limit=10)
    assert len(recent) == 1
    assert recent[0].action == "TEST_ACTION"
    assert recent[0].agent_name == "TestAgent"


def test_database_backup(temp_db):
    profile = ProfileRecord(id="p-backup", name="Backup Test", directory_name="b_dir")
    temp_db.create_profile(profile)

    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as backup_dir:
        backup_file = temp_db.backup_database(destination_dir=Path(backup_dir))
        assert backup_file.exists()
        assert backup_file.stat().st_size > 0
