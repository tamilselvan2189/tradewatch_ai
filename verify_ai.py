import asyncio
from ai_agent import TradeWatchAgent
from portfolio_service import PortfolioAnalysis, HoldingView

async def verify():
    print("🚀 Initializing TradeWatch AI Agent...")
    agent = TradeWatchAgent()
    
    # Mock some interesting portfolio data
    mock_analysis = PortfolioAnalysis(
        holdings=[],
        portfolio_value=100000,
        previous_value=98000,
        portfolio_change_pct=2.04,
        portfolio_pnl=2000,
        top_gainer=None,
        top_loser=None,
        top_3_gainers=[
            HoldingView("ZOMATO", 100, 120, 145, 125, "Tech", 14500, 16.0, 2500),
            HoldingView("RELIANCE", 10, 2450, 2550, 2500, "Energy", 25500, 2.0, 1000)
        ],
        top_3_losers=[
            HoldingView("HDFCBANK", 20, 1550, 1480, 1520, "Banking", 29600, -2.6, -1400)
        ],
        risk_insights=["High concentration in Banking sector."],
        drop_alerts=[]
    )
    
    print("🧠 Sending analysis data to OpenAI...")
    try:
        message = await agent.build_daily_message(mock_analysis)
        print("\n" + "="*40)
        print("📝 AI AGENT OUTPUT:")
        print("="*40)
        print(message)
        print("="*40)
    except Exception as e:
        print(f"❌ Error during AI verification: {str(e)}")

if __name__ == "__main__":
    asyncio.run(verify())
