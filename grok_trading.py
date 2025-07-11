from langchain_xai import ChatXAI
from langgraph.graph import StateGraph, END
from pydantic import BaseModel, constr
from typing import Literal
from datetime import datetime, UTC
import json
from btc_helper import get_btc_snapshot_alt

# 1️⃣ LLM clients ---------------------------------------------------
grok_analysis = ChatXAI(                      # Grok-4 with Live Search
    model="grok-3-mini-fast",
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
user_prompt_template = """
You are an expert cryptocurrency trading analyst with deep knowledge of market dynamics, technical analysis, and sentiment analysis.  
Your task is to deliver a precise, binary trading recommendation (LONG / SHORT) for high-frequency, 10×-leveraged Bitcoin trades entering *right now*. Give the analysis.

CURRENT CONTEXT
- Asset: Bitcoin (BTC)
- Trading style: High-frequency, 10× leverage
- Profit target: 0.3 % price move (≈ 3 % P&L with leverage)
- Time horizon: Minutes to hours
- Current UTC timestamp: {timestamp}

PRE-FETCHED MARKET SNAPSHOT  
```json
{snapshot_json}
```

FIELD MEANINGS

btc_spot_price — last traded spot price (USD)
price_change_pct_[1m|5m|15m] — momentum over rolling windows
ema9_1m, ema21_1m — fast / slow micro-trend averages
rsi_fast (7-period, 1 m) & rsi_standard (14-period, 5 m) — momentum gauges
macd_1m — MACD line value (12/26/9)
atr14_1m — 14-period ATR for volatility / stop sizing
vol_sma20_1m — 20-bar volume average
order_book_spread_pct — top-of-book bid/ask spread (%)
funding_rate — latest perp funding (sentiment-lite)
long_short_ratio — exchange-wide positioning bias (sentiment-lite)

ANALYSIS CHECKLIST

Trend & momentum: Examine EMA cross, MACD, RSI.
Volatility & liquidity: Confirm ATR and spread are compatible with a 0.3% scalp.
Sentiment bias: Funding rate & long/short ratio for crowd positioning.
Risk assessment: Note liquidation distance at 10× and any red flags in spread/ATR.
"""

def analyze_market(state: TradeState) -> dict:
    prompt = user_prompt_template.format(timestamp=datetime.now(UTC).strftime("%Y-%m-%d %H:%M:%S UTC"), snapshot_json=json.dumps(get_btc_snapshot_alt()))
    reply = grok_analysis.invoke(prompt)
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
