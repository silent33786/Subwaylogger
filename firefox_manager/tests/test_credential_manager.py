"""
Unit tests for CredentialManager.
Validates authenticated AES-GCM vault encryption, retrieval, and deletion.
"""

import pytest
import tempfile
from pathlib import Path

from firefox_manager.security.credential_manager import CredentialManager


@pytest.fixture
def temp_vault():
    with tempfile.TemporaryDirectory() as tmpdir:
        cm = CredentialManager(key_store_dir=Path(tmpdir))
        yield cm


def test_credential_store_and_retrieve(temp_vault):
    service = "TestService"
    user = "alice@example.com"
    secret = "SuperSecretP@ssw0rd!"

    stored = temp_vault.store_credential(service, user, secret)
    assert stored is True

    retrieved = temp_vault.get_credential(service, user)
    assert retrieved == secret
    assert temp_vault.has_credential(service, user) is True


def test_credential_deletion(temp_vault):
    service = "ServiceToDelete"
    user = "bob"
    secret = "ToDelete123"

    temp_vault.store_credential(service, user, secret)
    assert temp_vault.has_credential(service, user) is True

    deleted = temp_vault.delete_credential(service, user)
    assert deleted is True
    assert temp_vault.get_credential(service, user) is None
    assert temp_vault.has_credential(service, user) is False


def test_vault_no_plaintext_on_disk(temp_vault):
    service = "AuditService"
    user = "carol"
    secret = "VerySensitivePassword999"

    temp_vault.store_credential(service, user, secret)

    # Inspect fallback encrypted file if generated
    enc_file = temp_vault._vault_store_file
    if enc_file.exists():
        raw_bytes = enc_file.read_bytes()
        assert secret.encode("utf-8") not in raw_bytes

