from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any

from sqlalchemy import delete
from sqlalchemy.orm import Session

from models import HoldingCache, User


@dataclass
class HoldingView:
    symbol: str
    quantity: float
    avg_price: float
    current_price: float
    previous_close: float
    sector: str
    current_value: float
    day_change_pct: float
    pnl: float


@dataclass
class PortfolioAnalysis:
    holdings: list[HoldingView]
    portfolio_value: float
    previous_value: float
    portfolio_change_pct: float
    portfolio_pnl: float
    top_gainer: HoldingView | None
    top_loser: HoldingView | None
    top_3_gainers: list[HoldingView]
    top_3_losers: list[HoldingView]
    risk_insights: list[str]
    drop_alerts: list[HoldingView]


class PortfolioService:
    def upsert_holdings_cache(self, db: Session, user: User, holdings: list[dict[str, Any]]) -> None:
        db.execute(delete(HoldingCache).where(HoldingCache.user_id == user.id))
        for raw in holdings:
            # Official API uses 'trading_symbol', 'average_price'
            # current_price and previous_close might be in a different payload or nested
            row = HoldingCache(
                user_id=user.id,
                symbol=raw.get("trading_symbol") or raw.get("symbol"),
                qty=float(raw.get("quantity", 0)),
                avg_price=float(raw.get("average_price") or raw.get("avg_price") or 0),
                current_price=float(raw.get("current_price") or raw.get("day_close_price") or 0),
                previous_close=float(raw.get("previous_close") or raw.get("last_day_close") or 0),
                sector=raw.get("sector") or "Unknown",
                updated_at=datetime.utcnow(),
            )
            db.add(row)
        db.commit()

    def load_cached_holdings(self, db: Session, user: User) -> list[HoldingCache]:
        return db.query(HoldingCache).filter(HoldingCache.user_id == user.id).all()

    def analyze(self, holdings_rows: list[HoldingCache]) -> PortfolioAnalysis:
        holdings: list[HoldingView] = []
        portfolio_value = 0.0
        previous_value = 0.0

        for row in holdings_rows:
            current_value = row.qty * row.current_price
            prev_val = row.qty * row.previous_close
            day_change_pct = ((row.current_price - row.previous_close) / row.previous_close * 100) if row.previous_close else 0.0
            pnl = (row.current_price - row.avg_price) * row.qty
            holdings.append(
                HoldingView(
                    symbol=row.symbol,
                    quantity=row.qty,
                    avg_price=row.avg_price,
                    current_price=row.current_price,
                    previous_close=row.previous_close,
                    sector=row.sector or "Unknown",
                    current_value=current_value,
                    day_change_pct=day_change_pct,
                    pnl=pnl,
                )
            )
            portfolio_value += current_value
            previous_value += prev_val

        portfolio_change_pct = ((portfolio_value - previous_value) / previous_value * 100) if previous_value else 0.0
        portfolio_pnl = sum(h.pnl for h in holdings)
        top_gainer = max(holdings, key=lambda h: h.day_change_pct, default=None)
        top_loser = min(holdings, key=lambda h: h.day_change_pct, default=None)
        
        sorted_holdings = sorted(holdings, key=lambda h: h.day_change_pct, reverse=True)
        top_3_gainers = [h for h in sorted_holdings[:3] if h.day_change_pct > 0]
        top_3_losers = [h for h in sorted_holdings[::-1][:3] if h.day_change_pct < 0]

        risk_insights = self._risk_insights(holdings, portfolio_value)
        drop_alerts = [h for h in holdings if h.day_change_pct <= -2.0]

        return PortfolioAnalysis(
            holdings=holdings,
            portfolio_value=portfolio_value,
            previous_value=previous_value,
            portfolio_change_pct=portfolio_change_pct,
            portfolio_pnl=portfolio_pnl,
            top_gainer=top_gainer,
            top_loser=top_loser,
            top_3_gainers=top_3_gainers,
            top_3_losers=top_3_losers,
            risk_insights=risk_insights,
            drop_alerts=drop_alerts,
        )

    def inject_mock_data(self, db: Session, user: User) -> None:
        """Populate the cache with sample Indian stock data for demonstration."""
        mock_holdings = [
            {"trading_symbol": "RELIANCE", "quantity": 10, "average_price": 2450.0, "current_price": 2520.5, "previous_close": 2490.0, "sector": "Energy"},
            {"trading_symbol": "TCS", "quantity": 5, "average_price": 3600.0, "current_price": 3580.0, "previous_close": 3610.0, "sector": "IT"},
            {"trading_symbol": "ZOMATO", "quantity": 100, "average_price": 120.0, "current_price": 135.2, "previous_close": 115.0, "sector": "Tech/Consumer"},
            {"trading_symbol": "HDFCBANK", "quantity": 20, "average_price": 1550.0, "current_price": 1420.0, "previous_close": 1565.0, "sector": "Banking"},
        ]
        self.upsert_holdings_cache(db, user, mock_holdings)

    def _risk_insights(self, holdings: list[HoldingView], portfolio_value: float) -> list[str]:
        if not holdings or portfolio_value <= 0:
            return ["Insufficient data for concentration checks."]

        insights: list[str] = []
        sector_totals: dict[str, float] = {}

        for item in holdings:
            sector_totals[item.sector] = sector_totals.get(item.sector, 0.0) + item.current_value
            weight = item.current_value / portfolio_value * 100
            if weight > 25:
                insights.append(f"{item.symbol} concentration is high ({weight:.1f}%).")

        for sector, total in sector_totals.items():
            weight = total / portfolio_value * 100
            if weight > 40:
                insights.append(f"{sector} sector concentration is high ({weight:.1f}%).")

        simultaneous_drops = [item.symbol for item in holdings if item.day_change_pct <= -2.0]
        if len(simultaneous_drops) >= 2:
            insights.append(f"Multiple holdings dropping together: {', '.join(simultaneous_drops[:4])}.")

        if not insights:
            insights.append("No major concentration or correlated drop risks detected.")
        return insights
