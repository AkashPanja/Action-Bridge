"""Symmetric encryption for stored credentials (FR-2.2).

Secrets are encrypted at rest with Fernet (AES-128-CBC + HMAC). The master key
comes ONLY from the APP_ENCRYPTION_KEY environment variable — never the DB.
Expected format: a Fernet key (32 urlsafe-base64-encoded bytes).
Generate one with: python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
"""

import os

from cryptography.fernet import Fernet, InvalidToken

ENV_VAR = "APP_ENCRYPTION_KEY"


class EncryptionError(RuntimeError):
    pass


def get_fernet() -> Fernet:
    raw = os.getenv(ENV_VAR, "").strip()
    if not raw:
        raise EncryptionError(
            f"{ENV_VAR} is not set. Set it to a Fernet key to use stored credentials."
        )
    try:
        return Fernet(raw.encode())
    except (ValueError, TypeError) as exc:
        raise EncryptionError(f"{ENV_VAR} is not a valid Fernet key.") from exc


def encrypt_secret(plaintext: str) -> str:
    return get_fernet().encrypt(plaintext.encode()).decode()


def decrypt_secret(token: str) -> str:
    try:
        return get_fernet().decrypt(token.encode()).decode()
    except InvalidToken as exc:
        raise EncryptionError("Could not decrypt credential (wrong key or corrupt data).") from exc


def mask_secret(secret: str) -> str:
    """Write-only hint: last 4 characters only (FR-2.3)."""
    if not secret:
        return ""
    tail = secret[-4:] if len(secret) >= 4 else secret
    return f"****{tail}"
