from langchain_xai import ChatXAI
from langgraph.graph import StateGraph, END
from pydantic import BaseModel, constr
from typing import Literal

# 1️⃣ LLM clients ---------------------------------------------------
grok_analysis = ChatXAI(                      # Grok-4 with Live Search
    model="grok-4-latest",
    search_parameters={"mode": "on"},
    temperature=0.7,
)

class Decision(BaseModel):
    decision: Literal["long", "short"]
    reason: constr(max_length=120)

grok_json = ChatXAI(                          # Grok-3, no search
    model="grok-3-latest",
    temperature=0.3,
).with_structured_output(Decision, method="json_mode")

# 2️⃣ Graph state schema -------------------------------------------
class TradeState(BaseModel):
    analysis: str | None = None
    decision: str | None = None
    reason: str | None = None

# 3️⃣ Node 1 – run your prompt -------------------------------------
user_prompt = (
    "I am trading BTC with leverage (10x) in very short-term period. "
    "Will take profit when the price change 0.5%. "
    "Could you study the current market now (indicators/sentiments etc) and "
    "give me a simple binary suggestion: whether I should long or short if I enter *right now*?"
)

def analyze_market(state: TradeState) -> dict:
    reply = grok_analysis.invoke(user_prompt)
    return {"analysis": reply.content}

# 4️⃣ Node 2 – squeeze to JSON -------------------------------------
compress_tpl = """
Based **only** on the analysis below, output JSON exactly matching:
{{
  "decision": "long" | "short",
  "reason": "<≤120-char explanation>"
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
