# TradeWatch AI

Production-ready multi-user Telegram portfolio monitoring backend. Now migrated to the **Official Groww Trading API** with enhanced AI insights, secure MySQL storage, and restricted network support (Long Polling).

## ✨ New Features

- **Official Groww API**: Migrated from reverse-engineered endpoints to the stable, authorized Groww Trading API.
- **Smart Alerts**: 24-hour cooldown logic ensuring you only get one notification per stock drop per day.
- **Long Polling Mode**: Support for restricted networks (official laptops) without needing `ngrok` or public URLs.
- **Daily AI Pulse**: Professional Bloomberg-style portfolio analysis using OpenAI GPT-4o.
- **Demo Mode**: Test the entire bot flow with mock data using the `/demo` command.
- **AES-128 Encryption**: All session tokens are encrypted at rest in MySQL using Fernet.

## 🚀 Commands

- `/start` - Welcome and setup instructions.
- `/login` - Refresh your daily Groww session (requires manual approval on Groww website).
- `/portfolio` - Fetch and analyze your real equity holdings.
- `/demo` - **[TESTING]** Inject mock data to see a sample AI analysis.
- `/alerts` - Check for any significant drops in your holdings.
- `/logout` - Clear your session from the database.
- `/help` - List all available commands.

## 📁 Project Structure

- `main.py` - FastAPI app and background polling task management.
- `telegram_bot.py` - Command routing, **Long Polling loop**, and message logic.
- `groww_login.py` - Official API session generation & holdings fetch.
- `portfolio_service.py` - High-speed holdings analysis and mock data injection.
- `ai_agent.py` - Senior Portfolio Analyst (OpenAI) integration.
- `verify_ai.py` - **[NEW]** Standalone utility to verify AI commentary logic.
- `crypto.py` - Fernet encryption/decryption modules.
- `config.py` - Pydantic-driven environment settings.

## 🛠 Setup & Run

### 1. Environment Variables
Copy `.env.example` to `.env` and configure:
- `GROWW_API_KEY` & `GROWW_API_SECRET` (From Groww Cloud).
- `TELEGRAM_BOT_TOKEN` (@BotFather).
- `OPENAI_API_KEY` (For AI insights).
- `DATABASE_URL` (MySQL).
- `ENCRYPTION_KEY` (AES-128 key).
- `TELEGRAM_POLLING_ENABLED=True` (Set to True for restricted laptops).

### 2. Launch
```bash
# Install dependencies
pip install -r requirements.txt

# Start the server (includes background polling)
uvicorn main:app --host 0.0.0.0 --port 8007 --reload
```

### 3. Verify AI Agent
Run the standalone verification script to see a sample AI output:
```bash
python verify_ai.py
```

## 🔒 Security & Workflow
- **Daily Approval**: You must manually click **"Approve"** on your [Groww API Keys Page](https://groww.in/trade-api/api-keys) once every 24 hours.
- **Encryption**: Session tokens are encrypted before hitting the database. Plain-text tokens are never persisted.
- **Network Agnostic**: Using Long Polling ensures the bot works even behind corporate firewalls.

---

## 🏗 Requirements
- Python 3.10+
- MySQL 8.0+
- OpenAI API Access
- Groww Trading API Credentials
