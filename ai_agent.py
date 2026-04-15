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
        gainers_str = ", ".join([f"{h.symbol} ({h.day_change_pct:+.1f}%)" for h in analysis.top_3_gainers])
        losers_str = ", ".join([f"{h.symbol} ({h.day_change_pct:+.1f}%)" for h in analysis.top_3_losers])
        risk = analysis.risk_insights[0] if analysis.risk_insights else "Portfolio is balanced."

        system_prompt = (
            "You are a Senior Portfolio Analyst for TradeWatch AI. "
            "Your goal is to provide a concise, professional, and insightful summary of the daily performance for a retail investor. "
            "Use a premium, institutional tone (like Bloomberg or Reuters). "
            "Avoid generic filler words. Be sharp and analytical."
        )

        user_prompt = (
            "Analyze the following portfolio data and create a 6-8 line Telegram message.\n\n"
            f"Overall Change: {analysis.portfolio_change_pct:+.2f}%\n"
            f"Gainers today: {gainers_str or 'None'}\n"
            f"Losers today: {losers_str or 'None'}\n"
            f"Primary Risk: {risk}\n"
            f"Total Holdings: {len(analysis.holdings)}\n\n"
            "Requirements:\n"
            "1. Start with '📊 TradeWatch AI | Daily Pulse'.\n"
            "2. Provide a 2-sentence 'Market Pulse' interpretation of these moves.\n"
            "3. Use professional formatting with emojis.\n"
            "4. No financial advice (add a tiny 'Non-advisory' disclaimer at the bottom)."
        )

        try:
            # Use the newer chat completions API style if available, 
            # or keep wait for the client's current structure.
            response = await self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt}
                ],
                temperature=0.4,
            )
            return response.choices[0].message.content.strip()
        except Exception:
            return self._fallback_daily_message(analysis)

    async def build_drop_alert(self, analysis: PortfolioAnalysis, symbol: str, reason: str) -> str:
        holding = next((h for h in analysis.holdings if h.symbol == symbol), None)
        if not holding:
            return ""

        impact = (holding.current_value / analysis.portfolio_value * 100) if analysis.portfolio_value else 0.0
        
        system_prompt = "You are a TradeWatch Risk Alert bot. Be urgent, professional, and clear."
        user_prompt = (
            f"Generate a sharp 5-line risk alert for {holding.symbol}.\n"
            f"Drop: {holding.day_change_pct:.2f}%\n"
            f"Portfolio Impact: {impact:.1f}%\n"
            f"Market Context: {reason}\n\n"
            "Format:\n"
            "⚠️ RISK ALERT | TradeWatch AI\n"
            "Briefly summarize the drop and its significance to the total portfolio."
        )
        
        try:
            response = await self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt}
                ],
                temperature=0.3,
            )
            return response.choices[0].message.content.strip()
        except Exception:
            return self._fallback_drop_message(holding.symbol, holding.day_change_pct, impact, reason)

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
