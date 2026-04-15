from __future__ import annotations
import hashlib
import time

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any

import httpx
from sqlalchemy.orm import Session

from config import get_settings
from crypto import decrypt, encrypt
from models import User


@dataclass
class GrowwSession:
    token: str
    expires_at: datetime


class GrowwSessionManager:
    """
    Groww integration adapter.

    Replace endpoint paths in this class with the current Groww API paths used by your integration.
    OTP is accepted only in-memory and never persisted.
    """

    def __init__(self) -> None:
        self.settings = get_settings()
        self._client = httpx.AsyncClient(
            base_url=self.settings.groww_base_url,
            timeout=self.settings.groww_timeout_seconds,
            headers={
                "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                "X-API-VERSION": "1.0",
                "Content-Type": "application/json",
            },
        )

    def _generate_checksum(self, secret: str, timestamp: str) -> str:
        """Generates a SHA-256 checksum for api secret and timestamp."""
        input_str = secret + timestamp
        return hashlib.sha256(input_str.encode("utf-8")).hexdigest()

    async def create_session(self) -> GrowwSession:
        """Create a session using API Key and Secret flow (Approval)."""
        if not self.settings.groww_api_key or not self.settings.groww_api_secret:
            raise ValueError("GROWW_API_KEY and GROWW_API_SECRET must be configured")

        timestamp = str(int(time.time()))
        checksum = self._generate_checksum(self.settings.groww_api_secret, timestamp)

        payload = {
            "key_type": "approval",
            "checksum": checksum,
            "timestamp": timestamp
        }
        
        response = await self._client.post(
            "/v1/token/api/access",
            json=payload,
            headers={"Authorization": f"Bearer {self.settings.groww_api_key}"}
        )
        response.raise_for_status()
        data = response.json()
        
        token = data.get("token")
        if not token:
            raise ValueError("Groww access token missing in response")

        # Official tokens expire daily at 6:00 AM.
        expires_at = datetime.utcnow() + timedelta(minutes=self.settings.groww_session_ttl_minutes)
        return GrowwSession(token=token, expires_at=expires_at)

    async def request_otp(self, mobile: str) -> None:
        """Deprecated in official Trading API migration."""
        pass

    async def verify_otp_and_create_session(self, mobile: str, otp: str) -> GrowwSession:
        """Deprecated in official Trading API migration. Use create_session instead."""
        return await self.create_session()

    async def refresh_session(self, user: User) -> GrowwSession:
        if not self.settings.groww_api_key or not self.settings.groww_api_secret:
            raise ValueError("Missing GROWW_API credentials for refresh")
        return await self.create_session()

    async def get_holdings(self, user: User) -> list[dict[str, Any]]:
        if not user.groww_session:
            raise ValueError("Missing Groww session for user")
        response = await self._client.get(
            "/v1/holdings/user",
            headers={"Authorization": f"Bearer {decrypt(user.groww_session)}"},
        )
        if response.status_code == 401:
            raise PermissionError("Session expired")
        response.raise_for_status()
        data = response.json()
        # Official API returns payload with holdings list
        if data.get("status") == "SUCCESS":
            return data.get("payload", {}).get("holdings", [])
        return []

    async def ensure_session(self, db: Session, user: User) -> User:
        now = datetime.utcnow()
        if user.groww_session and user.session_expires_at and user.session_expires_at > now:
            return user

        refreshed = await self.refresh_session(user)
        user.groww_session = encrypt(refreshed.token)
        user.session_expires_at = refreshed.expires_at
        db.add(user)
        db.commit()
        db.refresh(user)
        return user

    async def close(self) -> None:
        await self._client.aclose()
