from langchain_xai import ChatXAI
from langgraph.graph import StateGraph, END
from pydantic import BaseModel, constr
from typing import Literal

# 1️⃣ LLM clients ---------------------------------------------------
grok_analysis = ChatXAI(                      # Grok-4 with Live Search
    model="grok-3-mini-fast",
    search_parameters={"mode": "on"},
    temperature=0.3,
)

class Decision(BaseModel):
    decision: Literal["long", "short"]
    reason: constr(max_length=120)

grok_json = ChatXAI(                          # Grok-3, no search
    model="grok-3-mini-fast",
    temperature=0.3,
).with_structured_output(Decision, method="json_mode")

# 2️⃣ Graph state schema -------------------------------------------
class TradeState(BaseModel):
    analysis: str | None = None
    decision: str | None = None
    reason: str | None = None

# 3️⃣ Node 1 – run your prompt -------------------------------------
user_prompt = """
You are an expert cryptocurrency trading analyst with deep knowledge of market dynamics, technical analysis, and sentiment analysis. Your role is to provide precise, actionable trading recommendations for high-frequency, leveraged Bitcoin trading.

CURRENT CONTEXT:
- Asset: Bitcoin (BTC)
- Trading Style: High-frequency, leveraged trading (10x leverage)
- Profit Target: 0.5% price movement
- Time Horizon: Very short-term (minutes to hours)
- Current Time: Please check the current date and time

REQUIRED ANALYSIS STEPS:
1. GET LATEST DATA: First, obtain the current BTC price, recent price action, and timestamp
2. TECHNICAL ANALYSIS: Analyze key indicators (RSI, MACD, moving averages, support/resistance levels)
3. MARKET SENTIMENT: Check current market sentiment, news, social media trends, and fear/greed index
4. VOLUME ANALYSIS: Examine trading volume patterns and liquidity
5. MACRO FACTORS: Consider any relevant macroeconomic events or announcements
6. RISK ASSESSMENT: Evaluate current market volatility and potential risks

TRADING PARAMETERS:
- Using 10x leverage means 0.5% price movement = 5% profit/loss
- Need to account for fees and slippage
- Must consider liquidation risks with leverage
- Focus on immediate market conditions (next 1-6 hours)

OUTPUT REQUIREMENT:
Based on your comprehensive analysis of current market conditions, provide a clear binary recommendation: should I go LONG or SHORT on BTC *right now*?

Include in your analysis:
- Current BTC price and recent price action
- Key technical levels and indicators
- Market sentiment and news impact
- Volume and liquidity conditions
- Risk factors and confidence level
- Specific entry reasoning for the recommended direction

Please conduct this analysis now using the most current market data available.
"""

def analyze_market(state: TradeState) -> dict:
    reply = grok_analysis.invoke(user_prompt)
    return {"analysis": reply.content}

# 4️⃣ Node 2 – squeeze to JSON -------------------------------------
compress_tpl = """
Based **only** on the comprehensive analysis below, extract the key trading decision and reasoning. 
Output JSON exactly matching this format:
{{
  "decision": "long" | "short",
  "reason": "<≤120-char explanation including price level, key indicator, or catalyst>"
}}

Analysis:
\"\"\"{analysis}\"\"\"
"""

def format_json(state: TradeState) -> dict:
    res: Decision = grok_json.invoke(compress_tpl.format(analysis=state.analysis))
    return {"decision": res.decision, "reason": res.reason}

def build_and_run_trading_graph():
    """
    Build and run the trading analysis graph.
    
    Returns:
        dict: The analysis result containing 'analysis', 'decision', and 'reason'
    """
    # Build the graph
    graph = StateGraph(TradeState)
    graph.add_node("analyze_market", analyze_market)
    graph.add_node("format_json", format_json)
    graph.set_entry_point("analyze_market")
    graph.add_edge("analyze_market", "format_json")
    graph.add_edge("format_json", END)
    bot = graph.compile()
    
    # Run the graph
    out = bot.invoke({})
    return out

# 5️⃣ Build & run the graph ----------------------------------------
if __name__ == "__main__":
    result = build_and_run_trading_graph()
    print(result)
    # ➜ {'analysis': '…', 'decision': 'long', 'reason': 'funding flipped positive…'}
