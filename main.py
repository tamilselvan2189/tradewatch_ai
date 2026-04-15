from __future__ import annotations

from fastapi import Depends, FastAPI, Header, HTTPException
from sqlalchemy.orm import Session

from config import get_settings
from db import Base, engine, get_db
from models import User
from scheduler import TradeWatchScheduler
from telegram_bot import TelegramBotService


settings = get_settings()
app = FastAPI(title=settings.app_name)
bot_service = TelegramBotService()
scheduler = TradeWatchScheduler(bot_service=bot_service)


@app.on_event("startup")
async def startup_event() -> None:
    Base.metadata.create_all(bind=engine)
    await bot_service.setup_webhook()
    scheduler.start()


@app.on_event("shutdown")
async def shutdown_event() -> None:
    scheduler.shutdown()
    await bot_service.close()


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post(settings.telegram_webhook_path)
async def telegram_webhook(
    payload: dict,
    db: Session = Depends(get_db),
    x_telegram_bot_api_secret_token: str | None = Header(default=None),
) -> dict[str, bool]:
    if x_telegram_bot_api_secret_token != settings.telegram_webhook_secret:
        raise HTTPException(status_code=403, detail="Invalid secret token")
    await bot_service.process_update(db, payload)
    return {"ok": True}


@app.get("/users")
async def list_users(db: Session = Depends(get_db)) -> list[dict[str, str | int | None]]:
    users = db.query(User).all()
    return [{"id": user.id, "telegram_id": user.telegram_id, "mobile": user.mobile} for user in users]
