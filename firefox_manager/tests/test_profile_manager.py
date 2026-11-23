"""
Unit tests for ProfileManager.
Tests duplicate name prevention, profile creation, and profile deletion.
"""

import pytest
import tempfile
from pathlib import Path
from unittest.mock import MagicMock

from firefox_manager.database.database import Database
from firefox_manager.browser.profile_storage import ProfileStorageManager
from firefox_manager.core.profile_manager import ProfileManager


@pytest.fixture
def isolated_profile_env(monkeypatch):
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmpdir:
        base = Path(tmpdir)
        db_path = base / "test.db"
        profiles_dir = base / "profiles"

        test_db = Database(db_path=db_path)
        test_storage = ProfileStorageManager(profiles_base_dir=profiles_dir)

        monkeypatch.setattr("firefox_manager.core.profile_manager.db", test_db)
        monkeypatch.setattr("firefox_manager.core.profile_manager.profile_storage", test_storage)

        pm = ProfileManager()
        yield pm, test_db, test_storage


def test_create_and_delete_profile(isolated_profile_env):
    pm, test_db, test_storage = isolated_profile_env

    profile = pm.create_profile(
        name="Developer_Profile",
        tags="coding, dev",
        notes="Testing profile manager",
    )

    assert profile.name == "Developer_Profile"
    assert test_storage.profile_exists(profile.directory_name)

    # Prevent duplicate name
    with pytest.raises(ValueError, match="already exists"):
        pm.create_profile(name="Developer_Profile")

    # Delete profile
    deleted = pm.delete_profile(profile.id, remove_disk_files=True)
    assert deleted is True
    assert not test_storage.profile_exists(profile.directory_name)
    assert test_db.get_profile(profile.id) is None
