"""Encrypts the daily Kite access token at rest (key derived from KITE_API_SECRET)."""
from __future__ import annotations

import base64
import hashlib

from cryptography.fernet import Fernet

from .config import SETTINGS


def _fernet() -> Fernet:
    seed = ("nifty-bot-state:" + SETTINGS.kite_api_secret).encode()
    return Fernet(base64.urlsafe_b64encode(hashlib.sha256(seed).digest()))


def encrypt(text: str) -> str:
    return _fernet().encrypt(text.encode()).decode()


def decrypt(blob: str) -> str:
    return _fernet().decrypt(blob.encode()).decode()
