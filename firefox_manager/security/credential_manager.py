"""
Enterprise Credential Manager.
Ensures zero plaintext password storage. Integrates directly with Windows
Credential Manager via the keyring interface, with an authenticated AES-256-GCM
fallback mechanism for headless / standalone environments.
"""

import os
import base64
import json
from pathlib import Path
from typing import Optional
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
from cryptography.hazmat.primitives import hashes

from firefox_manager.config.settings import settings

try:
    import keyring
    KEYRING_AVAILABLE = True
except ImportError:
    KEYRING_AVAILABLE = False


class CredentialManager:
    """Manages credentials securely without ever storing plaintext passwords."""

    APP_KEYRING_SERVICE_PREFIX = "FirefoxManager_"

    def __init__(self, key_store_dir: Optional[Path] = None):
        self.key_store_dir = Path(key_store_dir or (settings.data_dir / ".vault"))
        self.key_store_dir.mkdir(parents=True, exist_ok=True)
        self._master_key_file = self.key_store_dir / "vault.key"
        self._vault_store_file = self.key_store_dir / "vault.enc"
        self._ensure_encryption_key()

    def _ensure_encryption_key(self) -> None:
        """Initialize or load local AES-GCM master key for authenticated fallback."""
        if not self._master_key_file.exists():
            key = AESGCM.generate_key(bit_length=256)
            self._master_key_file.write_bytes(key)
        else:
            # Read existing key
            self._master_key = self._master_key_file.read_bytes()

    def _get_fallback_key(self) -> bytes:
        return self._master_key_file.read_bytes()

    def _service_key(self, service_name: str) -> str:
        return f"{self.APP_KEYRING_SERVICE_PREFIX}{service_name}"

    def store_credential(self, service_name: str, username: str, secret: str) -> bool:
        """
        Store a secret for a given service and username.
        Attempts Windows Credential Manager first; falls back to encrypted vault.
        """
        if not secret:
            return False

        stored = False
        service_id = self._service_key(service_name)

        if KEYRING_AVAILABLE:
            try:
                keyring.set_password(service_id, username, secret)
                stored = True
            except Exception:
                stored = False

        # If keyring fails or is unavailable, store in authenticated AES-256-GCM vault
        if not stored:
            self._store_fallback(service_id, username, secret)
            stored = True

        return stored

    def get_credential(self, service_name: str, username: str) -> Optional[str]:
        """Retrieve credential. Returns None if not found or on error."""
        service_id = self._service_key(service_name)

        if KEYRING_AVAILABLE:
            try:
                secret = keyring.get_password(service_id, username)
                if secret is not None:
                    return secret
            except Exception:
                pass

        # Try fallback vault
        return self._get_fallback(service_id, username)

    def delete_credential(self, service_name: str, username: str) -> bool:
        """Remove credential from both keyring and fallback vault."""
        service_id = self._service_key(service_name)
        deleted = False

        if KEYRING_AVAILABLE:
            try:
                keyring.delete_password(service_id, username)
                deleted = True
            except Exception:
                pass

        fallback_deleted = self._delete_fallback(service_id, username)
        return deleted or fallback_deleted

    def has_credential(self, service_name: str, username: str) -> bool:
        """Check whether credential exists."""
        return self.get_credential(service_name, username) is not None

    # =========================================================================
    # Fallback AES-256-GCM Encrypted Vault
    # =========================================================================

    def _load_vault(self) -> dict:
        if not self._vault_store_file.exists():
            return {}
        try:
            raw = self._vault_store_file.read_bytes()
            if len(raw) < 28:  # 12 bytes nonce + 16 bytes auth tag minimum
                return {}
            nonce = raw[:12]
            ciphertext = raw[12:]
            aesgcm = AESGCM(self._get_fallback_key())
            decrypted = aesgcm.decrypt(nonce, ciphertext, None)
            return json.loads(decrypted.decode("utf-8"))
        except Exception:
            return {}

    def _save_vault(self, data: dict) -> None:
        key = self._get_fallback_key()
        aesgcm = AESGCM(key)
        nonce = os.urandom(12)
        payload = json.dumps(data).encode("utf-8")
        ciphertext = aesgcm.encrypt(nonce, payload, None)
        self._vault_store_file.write_bytes(nonce + ciphertext)

    def _store_fallback(self, service_id: str, username: str, secret: str) -> None:
        vault = self._load_vault()
        key = f"{service_id}:{username}"
        vault[key] = secret
        self._save_vault(vault)

    def _get_fallback(self, service_id: str, username: str) -> Optional[str]:
        vault = self._load_vault()
        key = f"{service_id}:{username}"
        return vault.get(key)

    def _delete_fallback(self, service_id: str, username: str) -> bool:
        vault = self._load_vault()
        key = f"{service_id}:{username}"
        if key in vault:
            del vault[key]
            self._save_vault(vault)
            return True
        return False


# Global credential manager instance
credential_manager = CredentialManager()

