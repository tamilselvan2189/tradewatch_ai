from __future__ import annotations

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from sqlalchemy.orm import Session

from config import get_settings
from db import SessionLocal
from models import User
from telegram_bot import TelegramBotService


class TradeWatchScheduler:
    def __init__(self, bot_service: TelegramBotService) -> None:
        settings = get_settings()
        self.bot_service = bot_service
        self.scheduler = AsyncIOScheduler(timezone=settings.scheduler_timezone)

    def start(self) -> None:
        self.scheduler.add_job(self.daily_open_update, "cron", hour=9, minute=15, id="daily_open_update", replace_existing=True)
        self.scheduler.add_job(self.daily_close_update, "cron", hour=15, minute=30, id="daily_close_update", replace_existing=True)
        self.scheduler.add_job(self.realtime_drop_check, "interval", minutes=5, id="realtime_drop_check", replace_existing=True)
        self.scheduler.start()

    def shutdown(self) -> None:
        if self.scheduler.running:
            self.scheduler.shutdown(wait=False)

    async def daily_open_update(self) -> None:
        await self._broadcast_portfolio()

    async def daily_close_update(self) -> None:
        await self._broadcast_portfolio()

    async def realtime_drop_check(self) -> None:
        await self._broadcast_alerts()

    async def _broadcast_portfolio(self) -> None:
        db: Session = SessionLocal()
        try:
            users = db.query(User).filter(User.groww_session.isnot(None)).all()
            for user in users:
                fake_payload = {
                    "message": {
                        "chat": {"id": user.telegram_id},
                        "from": {"id": user.telegram_id},
                        "text": "/portfolio",
                    }
                }
                await self.bot_service.process_update(db, fake_payload)
        finally:
            db.close()

    async def _broadcast_alerts(self) -> None:
        db: Session = SessionLocal()
        try:
            users = db.query(User).filter(User.groww_session.isnot(None)).all()
            for user in users:
                fake_payload = {
                    "message": {
                        "chat": {"id": user.telegram_id},
                        "from": {"id": user.telegram_id},
                        "text": "/alerts",
                    }
                }
                await self.bot_service.process_update(db, fake_payload)
        finally:
            db.close()
