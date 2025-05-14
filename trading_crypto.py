#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ETH / XRP Perpetual-Futures bot (Binance UM)
-------------------------------------------
* Dependencies: pip install binance-futures-connector python-decouple
* Environment Variables:
    BINANCE_KEY, BINANCE_SECRET  –  API credentials
    POLLING_FREQUENCY            –  seconds, default 5
    LEVERAGE                     –  default 10
    ALLOCATION_PCT               –  default 0.06   (6%)
"""
import logging
import math
import os
import time
from decimal import Decimal, ROUND_DOWN
from typing import Tuple, Optional

from binance.error import ClientError
from binance.um_futures import UMFutures             # USDT-M Perpetual Interface  :contentReference[oaicite:0]{index=0}

from paging import send_notification
from utils import check_signal

###############################################################################
# Basic Utilities
###############################################################################
logger = logging.getLogger("futures-bot")
logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s | %(levelname)-7s | %(message)s")

API_KEY     = os.getenv("BINANCE_KEY")
API_SECRET  = os.getenv("BINANCE_SECRET")
POLL_SECS   = int(os.getenv("POLLING_FREQUENCY", "5"))
LEV         = int(os.getenv("LEVERAGE", "20"))
ALLOC_PCT   = Decimal(os.getenv("ALLOCATION_PCT", "0.06"))

# Only trade these two contracts
SYMBOLS = {"ETH.X": "ETHUSDT", "XRP.X": "XRPUSDT"}

client = UMFutures(key=API_KEY, secret=API_SECRET)   # HMAC Authentication  :contentReference[oaicite:1]{index=1}


def get_free_usdt() -> Decimal:
    """Available USDT balance (excluding position margin)"""
    balances = client.balance()          # Returns list
    print(balances)
    bal = next(b for b in balances if b["asset"] == "USDT")
    return Decimal(bal["balance"])


def position_size(symbol: str) -> Decimal:
    """Current position size (>0 for long, <0 for short, 0 for no position)"""
    pos = client.get_position_risk(symbol=symbol)[0]
    return Decimal(pos["positionAmt"])      # Position unit: coin


def round_step(value: Decimal, step: Decimal) -> str:
    """Truncate precision according to trading rules"""
    return str((value // step) * step)      # Decimal // Decimal == floor


def get_qty_precision(symbol: str) -> Decimal:
    """Read LOT_SIZE step size from trading rules"""
    info = client.exchange_info()
    fil = next(f for f in info["symbols"] if f["symbol"] == symbol)
    step = next(f for f in fil["filters"] if f["filterType"] == "LOT_SIZE")["stepSize"]
    return Decimal(step)


def calc_allocation(free_balance: Decimal) -> Decimal:
    """
    Calculate margin to be invested based on existing positions:
    - No positions: free_balance * ALLOC_PCT
    - With positions: Adjusts allocation based on number of existing positions
    """
    position_count = sum(1 for sym in SYMBOLS.values() if position_size(sym) > 0)
    denominator = Decimal("1") - ALLOC_PCT * position_count
    return (free_balance * ALLOC_PCT).quantize(
        Decimal("0.01"), rounding=ROUND_DOWN
    ) if position_count == 0 else (free_balance * ALLOC_PCT / denominator).quantize(
        Decimal("0.01"), rounding=ROUND_DOWN
    )


def set_leverage(symbol: str, leverage: int = LEV):
    """Only needs to be done once, can also be set in advance on the webpage"""
    try:
        client.change_leverage(symbol=symbol, leverage=leverage)
    except ClientError as ce:
        if ce.error_code != "-4046":        # -4046 = leveraged unchanged
            raise


def open_long(symbol: str, margin_usdt: Decimal):
    """Open long position at market price, invest margin_usdt with LEV leverage"""
    price = Decimal(client.ticker_price(symbol=symbol)["price"])
    notional = margin_usdt * LEV           # = Transaction amount (USDT)
    qty = notional / price                 # = Quantity (coins)
    step = get_qty_precision(symbol)
    qty_str = round_step(qty, step)
    logger.info(f"BUY {symbol} qty={qty_str} (≈{margin_usdt} USDT * {LEV}×)")
    client.new_order(symbol=symbol,
                     side="BUY",
                     type="MARKET",
                     quantity=qty_str,
                     newOrderRespType="RESULT")
    send_notification("BUY Signal", f"Opened long position for {symbol} with {margin_usdt} USDT * {LEV}x leverage", priority=0)


def close_position(symbol: str):
    """Close all long positions at market price"""
    qty = position_size(symbol)
    if qty == 0:
        return
    logger.info(f"SELL {symbol} qty={abs(qty)}  (Close)")
    client.new_order(symbol=symbol,
                     side="SELL",
                     type="MARKET",
                     quantity=str(abs(qty)),
                     reduceOnly="true")     # Prevent reverse position
    send_notification("SELL Signal", f"Closed position for {symbol} with quantity {abs(qty)}", priority=0)


###############################################################################
# Main Loop
###############################################################################
def main():
    logger.info("Starting crypto trading bot…")
    # Ensure leverage is set for both contracts
    for sym in SYMBOLS.values():
        set_leverage(sym)

    while True:
        try:
            signal_type, asset = check_signal()
            if signal_type is None:
                time.sleep(POLL_SECS)
                continue

            symbol = SYMBOLS[asset]
            have_pos = position_size(symbol) > 0

            if signal_type == "BUY":
                if have_pos:
                    logger.debug(f"→ already holding {symbol}, skip BUY")
                    continue
                free_usdt = get_free_usdt()
                alloc = calc_allocation(free_usdt)
                if alloc < Decimal("10"):
                    msg = f"Free balance too low (${alloc}), skip BUY"
                    logger.warning(msg)
                    send_notification("Low Balance Warning", msg, priority=0)
                    continue
                open_long(symbol, alloc)

            elif signal_type == "SELL":
                if not have_pos:
                    logger.debug(f"→ no {symbol} position, skip SELL")
                    continue
                close_position(symbol)

        except ClientError as ce:
            msg = f"Binance API error {ce.error_code}: {ce.error_message}"
            logger.error(msg)
            send_notification("ERROR Trading", msg, priority=1)
        except Exception as exc:
            msg = str(exc)
            logger.exception(exc)
            send_notification("ERROR Trading", msg, priority=1)

        time.sleep(POLL_SECS)


if __name__ == "__main__":
    main()
