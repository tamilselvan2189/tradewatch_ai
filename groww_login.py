from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
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
        )

    async def request_otp(self, mobile: str) -> None:
        payload = {"mobile": mobile}
        response = await self._client.post("/v1/login/request-otp", json=payload)
        response.raise_for_status()

    async def verify_otp_and_create_session(self, mobile: str, otp: str) -> GrowwSession:
        payload = {"mobile": mobile, "otp": otp}
        response = await self._client.post("/v1/login/verify-otp", json=payload)
        response.raise_for_status()
        data = response.json()
        token = data.get("session_token")
        if not token:
            raise ValueError("Groww session token missing in response")

        expires_at = datetime.now(timezone.utc) + timedelta(minutes=self.settings.groww_session_ttl_minutes)
        return GrowwSession(token=token, expires_at=expires_at)

    async def refresh_session(self, user: User) -> GrowwSession:
        if not user.groww_session:
            raise ValueError("No stored Groww session")
        response = await self._client.post("/v1/login/refresh", headers={"Authorization": f"Bearer {decrypt(user.groww_session)}"})
        response.raise_for_status()
        data = response.json()
        token = data.get("session_token", user.groww_session)
        expires_at = datetime.now(timezone.utc) + timedelta(minutes=self.settings.groww_session_ttl_minutes)
        return GrowwSession(token=token, expires_at=expires_at)

    async def get_holdings(self, user: User) -> list[dict[str, Any]]:
        if not user.groww_session:
            raise ValueError("Missing Groww session for user")
        response = await self._client.get("/v1/portfolio/holdings", headers={"Authorization": f"Bearer {decrypt(user.groww_session)}"})
        if response.status_code == 401:
            raise PermissionError("Session expired")
        response.raise_for_status()
        data = response.json()
        return data.get("holdings", [])

    async def ensure_session(self, db: Session, user: User) -> User:
        now = datetime.now(timezone.utc)
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
