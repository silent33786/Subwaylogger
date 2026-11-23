"""
Unit tests for Profile Storage Manager.
Tests directory isolation, user.js preference generation, lock handling, and cleanup.
"""

import pytest
import tempfile
from pathlib import Path

from firefox_manager.browser.profile_storage import ProfileStorageManager


@pytest.fixture
def temp_storage():
    with tempfile.TemporaryDirectory() as tmpdir:
        storage = ProfileStorageManager(profiles_base_dir=Path(tmpdir))
        yield storage


def test_create_profile_directory_and_user_js(temp_storage):
    dir_name = "test_profile_dir"
    profile_path = temp_storage.create_profile_directory(
        directory_name=dir_name,
        profile_id="pid-1234",
        profile_name="Finance Profile",
        custom_user_agent="Mozilla/5.0 CustomUA",
        proxy_server="127.0.0.1:8080",
    )

    assert profile_path.is_dir()
    meta_file = profile_path / "profile_meta.json"
    assert meta_file.exists()

    user_js = profile_path / "user.js"
    assert user_js.exists()
    content = user_js.read_text(encoding="utf-8")
    assert 'user_pref("general.useragent.override", "Mozilla/5.0 CustomUA");' in content
    assert 'user_pref("network.proxy.type", 1);' in content
    assert 'user_pref("network.cookie.lifetimePolicy", 0);' in content


def test_prevent_directory_overwrite(temp_storage):
    dir_name = "existing_profile"
    temp_storage.create_profile_directory(
        directory_name=dir_name,
        profile_id="pid-1",
        profile_name="First Profile",
    )

    # Attempt to create duplicate directory
    with pytest.raises(FileExistsError):
        temp_storage.create_profile_directory(
            directory_name=dir_name,
            profile_id="pid-2",
            profile_name="Second Profile",
        )


def test_stale_lock_removal(temp_storage):
    dir_name = "lock_test_profile"
    profile_path = temp_storage.create_profile_directory(
        directory_name=dir_name,
        profile_id="pid-lock",
        profile_name="Lock Test",
    )

    # Create dummy parent.lock
    lock_file = profile_path / "parent.lock"
    lock_file.write_text("lock")
    assert lock_file.exists()

    # Clean up stale lock
    cleaned = temp_storage.remove_stale_lock(dir_name)
    assert cleaned is True
    assert not lock_file.exists()


def test_calculate_disk_usage(temp_storage):
    dir_name = "size_test_profile"
    profile_path = temp_storage.create_profile_directory(
        directory_name=dir_name,
        profile_id="pid-size",
        profile_name="Size Test",
    )

    dummy_file = profile_path / "sample.data"
    dummy_file.write_bytes(b"A" * 1024)  # 1 KB

    usage = temp_storage.calculate_disk_usage(dir_name)
    assert usage >= 1024

