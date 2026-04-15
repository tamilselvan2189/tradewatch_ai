from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

import httpx
from sqlalchemy.orm import Session

from ai_agent import TradeWatchAgent
from config import get_settings
from crypto import encrypt
from groww_login import GrowwSessionManager
from models import User
from portfolio_service import PortfolioService


@dataclass
class TelegramUpdate:
    chat_id: int
    telegram_id: int
    text: str


class PendingLoginStore:
    def __init__(self, redis_url: str | None) -> None:
        self._memory: dict[int, str] = {}
        self._redis = None
        if redis_url:
            try:
                import redis.asyncio as redis  # type: ignore

                self._redis = redis.from_url(redis_url, encoding="utf-8", decode_responses=True)
            except Exception:
                # Keep service available even if Redis package/instance is unavailable.
                self._redis = None

    async def set_mobile(self, telegram_id: int, mobile: str, ttl_seconds: int = 300) -> None:
        if self._redis:
            await self._redis.set(f"pending_login:{telegram_id}", mobile, ex=ttl_seconds)
            return
        self._memory[telegram_id] = mobile

    async def get_mobile(self, telegram_id: int) -> str | None:
        if self._redis:
            return await self._redis.get(f"pending_login:{telegram_id}")
        return self._memory.get(telegram_id)

    async def clear_mobile(self, telegram_id: int) -> None:
        if self._redis:
            await self._redis.delete(f"pending_login:{telegram_id}")
            return
        self._memory.pop(telegram_id, None)

    async def close(self) -> None:
        if self._redis:
            await self._redis.aclose()


class TelegramBotService:
    def __init__(self) -> None:
        self.settings = get_settings()
        self.http = httpx.AsyncClient(timeout=20)
        self.groww = GrowwSessionManager()
        self.portfolio_service = PortfolioService()
        self.ai_agent = TradeWatchAgent()
        self.pending_login_store = PendingLoginStore(self.settings.redis_url)

    def parse_update(self, payload: dict[str, Any]) -> TelegramUpdate | None:
        msg = payload.get("message") or {}
        text = msg.get("text")
        chat_id = msg.get("chat", {}).get("id")
        telegram_id = msg.get("from", {}).get("id")
        if not text or not chat_id or not telegram_id:
            return None
        return TelegramUpdate(chat_id=chat_id, telegram_id=telegram_id, text=text.strip())

    async def process_update(self, db: Session, payload: dict[str, Any]) -> None:
        update = self.parse_update(payload)
        if not update:
            return

        parts = update.text.split()
        command = parts[0].lower()
        args = parts[1:]

        if command == "/start":
            await self.send_message(update.chat_id, "Welcome to TradeWatch AI.\nUse /login <mobile> to connect Groww.")
            return
        if command == "/help":
            await self.send_message(update.chat_id, "/start /login /portfolio /alerts /logout /help")
            return

        user = self._ensure_user(db, update.telegram_id)

        if command == "/login":
            await self._handle_login(db, user, update.chat_id, args)
        elif command == "/portfolio":
            await self._handle_portfolio(db, user, update.chat_id)
        elif command == "/alerts":
            await self._handle_alerts(db, user, update.chat_id)
        elif command == "/logout":
            await self._handle_logout(db, user, update.chat_id)
        else:
            await self.send_message(update.chat_id, "Unknown command. Use /help.")

    async def _handle_login(self, db: Session, user: User, chat_id: int, args: list[str]) -> None:
        if len(args) == 1 and args[0].isdigit() and len(args[0]) >= 10:
            mobile = args[0]
            await self.groww.request_otp(mobile)
            await self.pending_login_store.set_mobile(user.telegram_id, mobile)
            await self.send_message(chat_id, "OTP sent. Now run /login <otp>.")
            return

        if len(args) == 1 and args[0].isdigit():
            otp = args[0]
            mobile = await self.pending_login_store.get_mobile(user.telegram_id)
            if not mobile:
                await self.send_message(chat_id, "Start with /login <mobile> first.")
                return
            session = await self.groww.verify_otp_and_create_session(mobile, otp)
            await self.pending_login_store.clear_mobile(user.telegram_id)
            user.mobile = mobile
            user.groww_session = encrypt(session.token)
            user.session_expires_at = session.expires_at
            db.add(user)
            db.commit()
            await self.send_message(chat_id, "Groww login successful.")
            return

        await self.send_message(chat_id, "Usage: /login <mobile> then /login <otp>")

    async def _handle_portfolio(self, db: Session, user: User, chat_id: int) -> None:
        if not user.groww_session:
            await self.send_message(chat_id, "Not logged in. Use /login.")
            return
        try:
            user = await self.groww.ensure_session(db, user)
            raw_holdings = await self.groww.get_holdings(user)
            self.portfolio_service.upsert_holdings_cache(db, user, raw_holdings)
        except Exception:
            await self.send_message(chat_id, "Unable to fetch portfolio now. Try /login again.")
            return

        holdings_rows = self.portfolio_service.load_cached_holdings(db, user)
        analysis = self.portfolio_service.analyze(holdings_rows)
        message = await self.ai_agent.build_daily_message(analysis)
        await self.send_message(chat_id, message)

    async def _handle_alerts(self, db: Session, user: User, chat_id: int) -> None:
        holdings_rows = self.portfolio_service.load_cached_holdings(db, user)
        if not holdings_rows:
            await self.send_message(chat_id, "No cached holdings. Run /portfolio first.")
            return
        analysis = self.portfolio_service.analyze(holdings_rows)
        if analysis.portfolio_change_pct <= -1.0:
            await self.send_message(chat_id, f"⚠️ TradeWatch AI Alert\nPortfolio dropped {analysis.portfolio_change_pct:.2f}% today.")
            return
        if not analysis.drop_alerts:
            await self.send_message(chat_id, "No drop alerts currently.")
            return
        for dropped in analysis.drop_alerts[:3]:
            msg = await self.ai_agent.build_drop_alert(analysis, dropped.symbol, "Price action and broad market weakness")
            if msg:
                await self.send_message(chat_id, msg)

    async def _handle_logout(self, db: Session, user: User, chat_id: int) -> None:
        user.groww_session = None
        user.session_expires_at = datetime.now(timezone.utc)
        db.add(user)
        db.commit()
        await self.send_message(chat_id, "Logged out and Groww session cleared.")

    def _ensure_user(self, db: Session, telegram_id: int) -> User:
        user = db.query(User).filter(User.telegram_id == telegram_id).first()
        if user:
            return user
        user = User(telegram_id=telegram_id)
        db.add(user)
        db.commit()
        db.refresh(user)
        return user

    async def send_message(self, chat_id: int, message: str) -> None:
        url = f"https://api.telegram.org/bot{self.settings.telegram_bot_token}/sendMessage"
        payload = {"chat_id": chat_id, "text": message}
        await self.http.post(url, json=payload)

    async def setup_webhook(self) -> None:
        url = f"https://api.telegram.org/bot{self.settings.telegram_bot_token}/setWebhook"
        await self.http.post(url, json={"url": self.settings.telegram_webhook_url})

    async def close(self) -> None:
        await self.http.aclose()
        await self.groww.close()
        await self.pending_login_store.close()
