"""Encrypt / decrypt sensitive fields at rest using Fernet (AES-128-CBC)."""

from __future__ import annotations

from cryptography.fernet import Fernet

from config import get_settings


def _get_fernet() -> Fernet:
    key = get_settings().encryption_key
    return Fernet(key.encode())


def encrypt(plain_text: str) -> str:
    """Encrypt a plain-text string and return the ciphertext as a UTF-8 string."""
    return _get_fernet().encrypt(plain_text.encode()).decode()


def decrypt(cipher_text: str) -> str:
    """Decrypt a ciphertext string and return the original plain text."""
    return _get_fernet().decrypt(cipher_text.encode()).decode()
