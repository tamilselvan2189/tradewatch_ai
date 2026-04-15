# TradeWatch AI

Production-ready multi-user Telegram portfolio monitoring backend built with FastAPI, MySQL, Groww OTP session integration, OpenAI-powered summaries, and APScheduler alerts.

## Features

- Multi-user Telegram bot command workflow: `/start`, `/login`, `/portfolio`, `/alerts`, `/logout`, `/help`
- Groww OTP login flow (OTP only in memory; session token persisted per user)
- Portfolio fetch + cache for each user independently
- AI-generated daily and drop-alert Telegram messages
- Scheduled daily updates (9:15 AM and 3:30 PM IST) + realtime drop checks
- FastAPI webhook endpoint for Telegram

## Project Structure

- `main.py` - FastAPI app and webhook endpoints
- `telegram_bot.py` - Telegram command routing and message sending
- `groww_login.py` - Groww session manager and holdings fetch
- `portfolio_service.py` - holdings analysis and risk checks
- `ai_agent.py` - OpenAI message generation
- `scheduler.py` - APScheduler jobs
- `crypto.py` - Fernet encryption/decryption for sensitive data
- `db.py` - SQLAlchemy engine/session
- `models.py` - MySQL ORM models
- `config.py` - environment-driven settings

## Environment Variables

Copy `.env.example` to `.env` and fill values.

Required:

- `DATABASE_URL`
- `TELEGRAM_BOT_TOKEN`
- `TELEGRAM_WEBHOOK_SECRET`
- `TELEGRAM_WEBHOOK_URL`
- `OPENAI_API_KEY`
- `ENCRYPTION_KEY` — Fernet key for encrypting session tokens at rest

Generate an encryption key:

```bash
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

## Database Schema

`users`

- `id`
- `telegram_id`
- `mobile`
- `groww_session`
- `session_expires_at`
- `created_at`

`holdings_cache`

- `user_id`
- `symbol`
- `qty`
- `avg_price`
- `current_price`
- `previous_close`
- `sector`
- `updated_at`

## Local Run

1. Install dependencies:
   - `pip install -r requirements.txt`
2. Set env:
   - `cp .env.example .env`
3. Start server:
   - `uvicorn main:app --reload --host 0.0.0.0 --port 8000`

## Docker Run

1. Build:
   - `docker build -t tradewatch-ai .`
2. Run:
   - `docker run --env-file .env -p 8000:8000 tradewatch-ai`

## Telegram Setup

- Configure Telegram bot and point webhook to:
  - `https://your-domain.com/telegram/webhook`
- Use the same secret token in Telegram webhook and `TELEGRAM_WEBHOOK_SECRET`.

## Security Notes

- Password and OTP are never stored.
- Groww session tokens are **encrypted at rest** using Fernet (AES-128-CBC) before being saved to MySQL.
- The `ENCRYPTION_KEY` env variable is required — without it, tokens cannot be encrypted or decrypted.
- Only encrypted session tokens are persisted; plain-text tokens never touch the database.
- Each Telegram user is mapped to one independent Groww session.

## Production Notes

- Replace Groww endpoint paths in `groww_login.py` with current API paths from your integration.
- Prefer Alembic migrations instead of `create_all` for strict production change control.
- Add Redis queue/celery worker if scheduler load increases.
