from __future__ import annotations
import asyncio

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
            await self.send_message(
                update.chat_id, 
                "Welcome to TradeWatch AI.\n"
                "To connect Groww:\n"
                "1. Go to https://groww.in/trade-api/api-keys\n"
                "2. Click 'Approve' on your API key for today.\n"
                "3. Type /login here to start."
            )
            return
        if command == "/help":
            await self.send_message(update.chat_id, "/start /login /portfolio /demo /alerts /logout /help")
            return

        user = self._ensure_user(db, update.telegram_id)

        if command == "/login":
            await self._handle_login(db, user, update.chat_id, args)
        elif command == "/portfolio":
            await self._handle_portfolio(db, user, update.chat_id)
        elif command == "/demo":
            await self._handle_demo(db, user, update.chat_id)
        elif command == "/alerts":
            await self._handle_alerts(db, user, update.chat_id)
        elif command == "/logout":
            await self._handle_logout(db, user, update.chat_id)
        else:
            await self.send_message(update.chat_id, "Unknown command. Use /help.")

    async def _handle_login(self, db: Session, user: User, chat_id: int, args: list[str]) -> None:
        try:
            session = await self.groww.create_session()
            user.groww_session = encrypt(session.token)
            user.session_expires_at = session.expires_at
            db.add(user)
            db.commit()
            await self.send_message(chat_id, "Groww login successful (Official API).")
        except Exception as e:
            await self.send_message(
                chat_id, 
                f"Login failed: {str(e)}\n"
                "Make sure you have clicked 'Approve' for your API key on the Groww website today."
            )

    async def _handle_portfolio(self, db: Session, user: User, chat_id: int) -> None:
        if not user.groww_session:
            await self.send_message(chat_id, "Not logged in. Use /login (or /demo for test data).")
            return
        try:
            user = await self.groww.ensure_session(db, user)
            raw_holdings = await self.groww.get_holdings(user)
            if not raw_holdings:
                await self.send_message(chat_id, "Your Groww portfolio is currently empty. Try /demo to see a sample analysis!")
                return
            self.portfolio_service.upsert_holdings_cache(db, user, raw_holdings)
        except Exception:
            await self.send_message(chat_id, "Unable to fetch portfolio now. Try /login again.")
            return

        await self._render_analysis(db, user, chat_id)

    async def _handle_demo(self, db: Session, user: User, chat_id: int) -> None:
        self.portfolio_service.inject_mock_data(db, user)
        await self.send_message(chat_id, "🚀 Demo Mode: Mock portfolio data injected.")
        await self._render_analysis(db, user, chat_id)

    async def _render_analysis(self, db: Session, user: User, chat_id: int) -> None:
        holdings_rows = self.portfolio_service.load_cached_holdings(db, user)
        if not holdings_rows:
            await self.send_message(chat_id, "No data available.")
            return
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
        """Sets up a webhook if configured, otherwise deletes any existing webhook to enable polling."""
        if self.settings.telegram_webhook_url:
            url = f"https://api.telegram.org/bot{self.settings.telegram_bot_token}/setWebhook"
            await self.http.post(url, json={"url": self.settings.telegram_webhook_url})
        else:
            # Delete webhook to enable long polling
            url = f"https://api.telegram.org/bot{self.settings.telegram_bot_token}/deleteWebhook"
            await self.http.post(url)

    async def poll_updates(self, db_factory: Any) -> None:
        """Continuously polls Telegram for updates (Long Polling)."""
        print("DEBUG: Telegram Polling Started...")
        offset = 0
        url = f"https://api.telegram.org/bot{self.settings.telegram_bot_token}/getUpdates"
        
        while True:
            try:
                params = {"offset": offset, "timeout": 30}
                response = await self.http.get(url, params=params, timeout=40)
                if response.status_code == 200:
                    data = response.json()
                    for update_raw in data.get("result", []):
                        offset = update_raw["update_id"] + 1
                        # Process update in a new DB session
                        with db_factory() as db:
                            await self.process_update(db, update_raw)
                elif response.status_code == 409:
                    # Webhook still active, try to delete it again
                    await self.setup_webhook()
            except Exception as e:
                # Log error and wait before retry
                print(f"Polling error: {str(e)}")
            
            await asyncio.sleep(1)

    async def close(self) -> None:
        await self.http.aclose()
        await self.groww.close()
