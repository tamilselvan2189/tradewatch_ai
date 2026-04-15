from __future__ import annotations

from openai import AsyncOpenAI

from config import get_settings
from portfolio_service import PortfolioAnalysis


class TradeWatchAgent:
    def __init__(self) -> None:
        settings = get_settings()
        self.model = settings.openai_model
        self.client = AsyncOpenAI(api_key=settings.openai_api_key)

    async def build_daily_message(self, analysis: PortfolioAnalysis) -> str:
        gainer = f"{analysis.top_gainer.symbol} {analysis.top_gainer.day_change_pct:+.2f}%" if analysis.top_gainer else "NA"
        loser = f"{analysis.top_loser.symbol} {analysis.top_loser.day_change_pct:+.2f}%" if analysis.top_loser else "NA"
        risk = analysis.risk_insights[0] if analysis.risk_insights else "No major risks detected."

        prompt = (
            "Create a Telegram-ready portfolio insight message in at most 8 lines.\n"
            "No financial advice. Only insights.\n"
            "Use this structure exactly:\n"
            "📊 TradeWatch AI\n"
            "Portfolio: {portfolio_change}\n"
            "Top gainer:\n"
            "{gainer}\n"
            "Top loser:\n"
            "{loser}\n"
            "Risk:\n"
            "{risk}\n"
            "Holdings: {count}\n\n"
            f"portfolio_change={analysis.portfolio_change_pct:+.2f}%\n"
            f"gainer={gainer}\n"
            f"loser={loser}\n"
            f"risk={risk}\n"
            f"count={len(analysis.holdings)}"
        )
        response = await self.client.responses.create(
            model=self.model,
            input=[{"role": "user", "content": prompt}],
            temperature=0.1,
        )
        text = response.output_text.strip()
        return text or self._fallback_daily_message(analysis)

    async def build_drop_alert(self, analysis: PortfolioAnalysis, symbol: str, reason: str) -> str:
        holding = next((h for h in analysis.holdings if h.symbol == symbol), None)
        if not holding:
            return ""

        impact = (holding.current_value / analysis.portfolio_value * 100) if analysis.portfolio_value else 0.0
        prompt = (
            "Generate short Telegram alert in max 7 lines with emojis.\n"
            "No recommendations.\n"
            "Format:\n"
            "⚠️ TradeWatch AI Alert\n"
            "{symbol} dropped {percent}\n"
            "Impact:\n"
            "{impact}\n"
            "Reason:\n"
            "{reason}\n\n"
            f"symbol={holding.symbol}\n"
            f"percent={holding.day_change_pct:.2f}%\n"
            f"impact={impact:.1f}% of portfolio\n"
            f"reason={reason}"
        )
        response = await self.client.responses.create(
            model=self.model,
            input=[{"role": "user", "content": prompt}],
            temperature=0.1,
        )
        text = response.output_text.strip()
        return text or self._fallback_drop_message(holding.symbol, holding.day_change_pct, impact, reason)

    def _fallback_daily_message(self, analysis: PortfolioAnalysis) -> str:
        gainer = f"{analysis.top_gainer.symbol} {analysis.top_gainer.day_change_pct:+.2f}%" if analysis.top_gainer else "NA"
        loser = f"{analysis.top_loser.symbol} {analysis.top_loser.day_change_pct:+.2f}%" if analysis.top_loser else "NA"
        risk = analysis.risk_insights[0] if analysis.risk_insights else "No major risks."
        return (
            "📊 TradeWatch AI\n"
            f"Portfolio: {analysis.portfolio_change_pct:+.2f}%\n"
            "Top gainer:\n"
            f"{gainer}\n"
            "Top loser:\n"
            f"{loser}\n"
            "Risk:\n"
            f"{risk}\n"
            f"Holdings: {len(analysis.holdings)}"
        )

    def _fallback_drop_message(self, symbol: str, pct: float, impact: float, reason: str) -> str:
        return (
            "⚠️ TradeWatch AI Alert\n"
            f"{symbol} dropped {pct:.2f}%\n"
            "Impact:\n"
            f"{impact:.1f}% of portfolio\n"
            "Reason:\n"
            f"{reason}"
        )
