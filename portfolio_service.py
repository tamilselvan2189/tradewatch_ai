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
    risk_insights: list[str]
    drop_alerts: list[HoldingView]


class PortfolioService:
    def upsert_holdings_cache(self, db: Session, user: User, holdings: list[dict[str, Any]]) -> None:
        db.execute(delete(HoldingCache).where(HoldingCache.user_id == user.id))
        for raw in holdings:
            row = HoldingCache(
                user_id=user.id,
                symbol=raw["symbol"],
                qty=float(raw["quantity"]),
                avg_price=float(raw["avg_price"]),
                current_price=float(raw["current_price"]),
                previous_close=float(raw["previous_close"]),
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
            risk_insights=risk_insights,
            drop_alerts=drop_alerts,
        )

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
