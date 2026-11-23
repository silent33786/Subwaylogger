"""
Enterprise Credential Manager.
Ensures zero plaintext password storage. Integrates directly with Windows
Credential Manager via the keyring interface, with an authenticated AES-256-GCM
fallback mechanism for headless / standalone environments.

Vault-key handling (fixed): the old code generated a random AES key and
wrote it as a plaintext file (vault.key) next to the encrypted vault
(vault.enc), so anyone who could read the folder could decrypt every
stored password. The key is now stored in the OS credential store
(keyring) first. A file fallback exists only when keyring is unavailable,
is written with owner-only permissions (0o600), and is documented as
weaker - see FIXES.md. The key is a random 256-bit key generated once
with AESGCM.generate_key; no password-based derivation is claimed, so
the previously imported-but-unused PBKDF2 code has been removed.
"""

import base64
import os
import json
from pathlib import Path
from typing import Optional
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from firefox_manager.config.settings import settings

try:
    import keyring
    KEYRING_AVAILABLE = True
except ImportError:
    KEYRING_AVAILABLE = False


class CredentialManager:
    """Manages credentials securely without ever storing plaintext passwords."""

    APP_KEYRING_SERVICE_PREFIX = "FirefoxManager_"
    VAULT_KEY_SERVICE = "FirefoxManager_vault_key"
    VAULT_KEY_USERNAME = "vault-master-key"

    def __init__(self, key_store_dir: Optional[Path] = None):
        self.key_store_dir = Path(key_store_dir or (settings.data_dir / ".vault"))
        self.key_store_dir.mkdir(parents=True, exist_ok=True)
        self._master_key_file = self.key_store_dir / "vault.key"
        self._vault_store_file = self.key_store_dir / "vault.enc"
        self._master_key: bytes = b""
        self._key_in_keyring = False
        self._ensure_encryption_key()

    def _ensure_encryption_key(self) -> None:
        """Initialize or load local AES-GCM master key for authenticated fallback.

        Always sets self._master_key (the old code only set it when the
        file already existed, leaving the attribute missing on a fresh
        vault). Order: keyring first, then an existing file, then generate
        a new key and try keyring first before writing a file.
        """
        # 1. Try the OS credential store first.
        if KEYRING_AVAILABLE:
            try:
                stored = keyring.get_password(self.VAULT_KEY_SERVICE, self.VAULT_KEY_USERNAME)
                if stored:
                    self._master_key = base64.b64decode(stored)
                    self._key_in_keyring = True
                    return
            except Exception:
                pass

        # 2. Existing file fallback (from an older install).
        if self._master_key_file.exists():
            self._master_key = self._master_key_file.read_bytes()
            # Migrate it into keyring when possible so the file can be removed.
            if KEYRING_AVAILABLE:
                try:
                    keyring.set_password(
                        self.VAULT_KEY_SERVICE, self.VAULT_KEY_USERNAME,
                        base64.b64encode(self._master_key).decode("ascii"),
                    )
                    self._key_in_keyring = True
                except Exception:
                    pass
            return

        # 3. Generate a fresh key.
        self._master_key = AESGCM.generate_key(bit_length=256)
        if KEYRING_AVAILABLE:
            try:
                keyring.set_password(
                    self.VAULT_KEY_SERVICE, self.VAULT_KEY_USERNAME,
                    base64.b64encode(self._master_key).decode("ascii"),
                )
                self._key_in_keyring = True
                return
            except Exception:
                pass
        # Last resort only: file fallback, owner-only permissions.
        # WARNING: a file-stored key is weaker than the OS vault - anyone
        # with read access to this folder can decrypt the vault. Prefer
        # a machine with Windows Credential Manager / keyring available.
        self._master_key_file.write_bytes(self._master_key)
        try:
            os.chmod(self._master_key_file, 0o600)
        except Exception:
            pass

    def _get_fallback_key(self) -> bytes:
        # Always the in-memory key set by _ensure_encryption_key(), never
        # a silent re-read that could return a different / missing key.
        if not self._master_key:
            self._ensure_encryption_key()
        return self._master_key

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
        try:
            os.chmod(self._vault_store_file, 0o600)
        except Exception:
            pass

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
