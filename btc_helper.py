import time, json, requests, pandas as pd

# 🔑  put your secrets here
TAAPI_SECRET   = ""
TAAPI_BASE     = "https://api.taapi.io"
BYBIT_BASE     = "https://api.bybit.com"
COINBASE_BOOK  = "https://api.exchange.coinbase.com/products/BTC-USD/book"

SYMBOL_TAAPI   = "BTC/USDT"     # works even if you trade elsewhere
EXCHANGE_TAAPI = "coinbase"     # any exchange TAAPI supports
INTERVAL       = "1m"

def get_btc_snapshot_alt():
    # ---------- 1) TAAPI bulk: 2 constructs --------------------------
    bulk_payload = {
        "secret": TAAPI_SECRET,
        "construct": [
            {   # ---- 1-minute indicators ----
                "exchange": "coinbase",
                "symbol":   "BTC/USDT",
                "interval": "1m",
                "indicators": [
                    {"id": "ema9",  "indicator": "ema",  "period": 9},
                    {"id": "ema21", "indicator": "ema",  "period": 21},
                    {"id": "rsi7",  "indicator": "rsi",  "period": 7},
                    {"id": "macd",  "indicator": "macd",
                     "fast": 12, "slow": 26, "signal": 9},
                    {"id": "atr14", "indicator": "atr",  "period": 14}
                ]
            },
            {   # ---- 5-minute RSI 14 ----
                "exchange": "coinbase",
                "symbol":   "BTC/USDT",
                "interval": "5m",
                "indicators": [
                    {"id": "rsi14", "indicator": "rsi", "period": 14}
                ]
            }
        ]
    }

    taapi_resp = requests.post(
        f"{TAAPI_BASE}/bulk", json=bulk_payload, timeout=8
    ).json()

    if "data" not in taapi_resp:
        raise RuntimeError(f"TAAPI error → {taapi_resp}")

    # flatten the list into {id: value}
    tmap = {}
    for item in taapi_resp["data"]:
        if item["errors"]:
            raise RuntimeError(
                f"TAAPI calc error on {item['id']} → {item['errors']}"
            )
        val = item["result"]
        # MACD returns three values
        if "valueMACD" in val:
            tmap["macd"] = val["valueMACD"]
        else:
            tmap[item["id"]] = val["value"]

    # ---------- 2) 20 latest 1-min candles (for price & volume SMA20)
    candles = requests.get(
        f"{TAAPI_BASE}/candles",
        params=dict(
            secret=TAAPI_SECRET, exchange="coinbase",
            symbol="BTC/USDT", interval="1m", period=20
        ),
        timeout=8
    ).json()

    df = pd.DataFrame(candles)
    df["close"]  = pd.to_numeric(df["close"])
    df["volume"] = pd.to_numeric(df["volume"])

    price_now = df["close"].iloc[-1]
    pct_1m  = (df["close"].iloc[-1] - df["close"].iloc[-2])   / df["close"].iloc[-2]  * 100
    pct_5m  = (df["close"].iloc[-1] - df["close"].iloc[-6])   / df["close"].iloc[-6]  * 100
    pct_15m = (df["close"].iloc[-1] - df["close"].iloc[-16])  / df["close"].iloc[-16] * 100
    vol_sma20 = df["volume"].mean()

    # ---------- 3) Coinbase best bid/ask spread ---------------------
    book = requests.get(COINBASE_BOOK, params={"level": 1}, timeout=4).json()
    best_bid, best_ask = map(float, (book["bids"][0][0], book["asks"][0][0]))
    spread_pct = (best_ask - best_bid) / ((best_bid + best_ask) / 2) * 100

    # --- funding rate -------------------------------------------------
    funding = float(
        requests.get(
            f"{BYBIT_BASE}/v5/market/funding/history",
            params={
                "category": "linear",
                "symbol":   "BTCUSDT",
                "limit":    1
            }, timeout=4
        ).json()["result"]["list"][0]["fundingRate"]
    )

    # --- long/short ratio --------------------------------------------
    lsr = float(
        requests.get(
            f"{BYBIT_BASE}/v5/market/account-ratio",
            params={
                "category": "linear",
                "symbol":   "BTCUSDT",
                "period":   "15min",
                "limit":    1
            }, timeout=4
        ).json()["result"]["list"][0]["buyRatio"]
)

    # ---------- 5) Package -----------------------------------------
    snapshot = {
        "timestamp_ms": int(time.time() * 1000),
        "btc_spot_price": price_now,
        "price_change_pct_1m":  pct_1m,
        "price_change_pct_5m":  pct_5m,
        "price_change_pct_15m": pct_15m,
        "ema9_1m":  tmap["ema9"],
        "ema21_1m": tmap["ema21"],
        "rsi_fast": tmap["rsi7"],
        "rsi_standard": tmap["rsi14"],
        "macd_1m":  tmap["macd"],
        "atr14_1m": tmap["atr14"],
        "vol_sma20_1m": vol_sma20,
        "order_book_spread_pct": spread_pct,
        "funding_rate": float(funding),
        "long_short_ratio": float(lsr)
    }
    return snapshot

if __name__ == "__main__":
    print(json.dumps(get_btc_snapshot_alt(), indent=2))