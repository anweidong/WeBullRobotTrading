#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
HyperLiquid BTC/USD Perpetual Futures Bot

This bot trades BTC perpetual futures on HyperLiquid with 10x leverage.
It uses the Grok trading graph to make trading decisions and implements
take profit (0.5%) and stop loss (0.3%) for each position.

Dependencies:
    pip install --upgrade hyperliquid-python-sdk eth-account python-dotenv web3
"""
import os
import sys
import time
import logging
from decimal import Decimal, ROUND_DOWN, ROUND_UP
from dotenv import load_dotenv

from eth_account import Account
from hyperliquid.info import Info
from hyperliquid.exchange import Exchange
from hyperliquid.utils import constants

# Import the Grok trading decision function
from grok_trading import build_and_run_trading_graph
from paging import send_notification

# Load environment variables from .env file
load_dotenv()

# --- Configuration ---
SIGNING_KEY_HEX = os.getenv("HL_SIGNING_KEY")
MASTER_WALLET = os.getenv("HL_PUBLIC_KEY")
POLL_SECS = 5  # Check every 5 seconds
LEVERAGE = 10  # Use 10x leverage
SYMBOL = "BTC"
TAKE_PROFIT_PCT = Decimal("0.005")  # 0.5%
STOP_LOSS_PCT = Decimal("0.003")    # 0.3%

# Logging setup
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s | %(levelname)-8s | %(message)s"
)
logger = logging.getLogger("hl-btc-bot")

# Initialize Info client (for read-only data) and wallet details
if not all([SIGNING_KEY_HEX, MASTER_WALLET]):
    logger.error("FATAL: Ensure HL_SIGNING_KEY and HL_PUBLIC_KEY are set in your .env file.")
    sys.exit(1)

decoded_key = Account.from_key(SIGNING_KEY_HEX)
info = Info(constants.MAINNET_API_URL, skip_ws=True)
# Initialize Exchange client from SDK for all trading actions
exchange = Exchange(decoded_key, constants.MAINNET_API_URL, account_address=MASTER_WALLET)


# --- Core Functions ---

def set_leverage(symbol: str, leverage: int, is_cross_margin: bool = False):
    """
    Sets the leverage for a given asset using the Python SDK.
    """
    logger.info(f"Setting leverage for {symbol} to {leverage}x using SDK...")
    try:
        response = exchange.update_leverage(leverage, symbol, is_cross_margin)
        logger.debug(f"Leverage update response: {response}")

        if response["status"] == "ok":
            logger.info(f"✅ Successfully set leverage for {symbol} to {leverage}x.")
        else:
            raise ValueError(f"Leverage update not confirmed in response: {response}")
    except Exception as e:
        logger.exception("Failed to set leverage")
        send_notification(f"ERROR setting {symbol} leverage", str(e), priority=1)
        sys.exit(1)


def get_market_price() -> Decimal:
    """
    Fetch the mid-market price for the configured SYMBOL.
    """
    mids = info.all_mids()
    price_str = mids.get(SYMBOL)
    if price_str is None:
        raise Exception(f"{SYMBOL} mid-price not found in API response")
    return Decimal(price_str)


def get_account_value() -> Decimal:
    """
    Retrieve total account value in USD from clearinghouse state.
    """
    state = info.user_state(MASTER_WALLET)
    account_value_str = state["withdrawable"]
    return Decimal(str(account_value_str))


def get_current_position():
    """
    Get the current position for the configured symbol.
    Returns a tuple of (size, entry_price) or (0, 0) if no position.
    """
    try:
        user_state = info.user_state(MASTER_WALLET)
        positions = user_state.get("assetPositions", [])
        
        for position in positions:
            if position["position"]["coin"] == SYMBOL:
                size = Decimal(position["position"]["szi"])
                entry_price = Decimal(position["position"]["entryPx"])
                return size, entry_price
        
        return Decimal("0"), Decimal("0")
    except Exception as e:
        logger.exception("Error getting current position")
        raise e


def round_to_tick_size(price: Decimal, tick_size: Decimal, rounding=ROUND_DOWN) -> Decimal:
    """
    Rounds a price to the nearest valid tick size.
    """
    return (price / tick_size).quantize(Decimal("1"), rounding=rounding) * tick_size


def open_position(is_long: bool, size_usd: Decimal, tick_size: Decimal):
    """
    Open a position with take profit and stop loss orders.
    """
    position_type = "LONG" if is_long else "SHORT"
    try:
        market_price = get_market_price()
        size_btc = (size_usd * LEVERAGE / market_price).quantize(Decimal("0.0001"), rounding=ROUND_DOWN)

        min_size = Decimal("0.001")
        if size_btc < min_size:
            raise ValueError(f"Order size {size_btc} BTC is below minimum {min_size} BTC")

        logger.info(f"Calculated order: {size_btc:.4f} BTC (${size_usd:.2f} @ ${market_price:.2f})")
        
        # Calculate an aggressive price for market order
        price_modifier = Decimal("1.05") if is_long else Decimal("0.95")
        raw_limit_price = market_price * price_modifier
        rounding_method = ROUND_UP if is_long else ROUND_DOWN
        limit_price = round_to_tick_size(raw_limit_price, tick_size, rounding=rounding_method)
        
        direction_str = "BUY" if is_long else "SELL"
        logger.info(f"Using aggressive limit {direction_str} price: ${limit_price} (Tick Size: {tick_size})")

        # Main order
        main_resp = exchange.order(
            SYMBOL,
            is_long,  # is_buy
            float(size_btc),
            float(limit_price),
            {"limit": {"tif": "Ioc"}}
        )
        logger.debug(f"Main order response: {main_resp}")

        # Detailed error checking for main order
        if main_resp["status"] != "ok":
            raise ValueError(f"Main order request failed: {main_resp}")
        
        main_statuses = main_resp.get("response", {}).get("data", {}).get("statuses", [])
        for status in main_statuses:
            if "error" in status:
                raise ValueError(f"Main order failed: {status['error']}")

        # Calculate take profit and stop loss prices
        if is_long:
            tp_price = market_price * (Decimal("1") + TAKE_PROFIT_PCT)
            sl_price = market_price * (Decimal("1") - STOP_LOSS_PCT)
        else:
            tp_price = market_price * (Decimal("1") - TAKE_PROFIT_PCT)
            sl_price = market_price * (Decimal("1") + STOP_LOSS_PCT)
            
        tp_price = round_to_tick_size(tp_price, tick_size)
        sl_price = round_to_tick_size(sl_price, tick_size)
        
        # Take profit order
        tp_resp = exchange.order(
            SYMBOL,
            not is_long,  # opposite direction to close
            float(size_btc),
            float(tp_price),
            {
                "trigger": {
                    "isMarket": True, 
                    "triggerPx": float(tp_price), 
                    "tpsl": "tp"
                }
            },
            reduce_only=True
        )
        logger.debug(f"Take profit order response: {tp_resp}")

        # Detailed error checking for take profit order
        if tp_resp["status"] != "ok":
            raise ValueError(f"Take profit order request failed: {tp_resp}")
        
        tp_statuses = tp_resp.get("response", {}).get("data", {}).get("statuses", [])
        for status in tp_statuses:
            if "error" in status:
                raise ValueError(f"Take profit order failed: {status['error']}")

        # Stop loss order
        sl_resp = exchange.order(
            SYMBOL,
            not is_long,  # opposite direction to close
            float(size_btc),
            float(sl_price),
            {
                "trigger": {
                    "isMarket": True, 
                    "triggerPx": float(sl_price), 
                    "tpsl": "sl"
                }
            },
            reduce_only=True
        )
        logger.debug(f"Stop loss order response: {sl_resp}")

        # Detailed error checking for stop loss order
        if sl_resp["status"] != "ok":
            raise ValueError(f"Stop loss order request failed: {sl_resp}")
        
        sl_statuses = sl_resp.get("response", {}).get("data", {}).get("statuses", [])
        for status in sl_statuses:
            if "error" in status:
                raise ValueError(f"Stop loss order failed: {status['error']}")

        logger.info(f"✅ Opened {position_type} {size_btc:.4f} {SYMBOL} @ ~${market_price:.2f} with TP: ${tp_price:.2f} SL: ${sl_price:.2f}")
        send_notification(f"{position_type} OPENED", 
                         f"{size_btc:.4f} {SYMBOL} @ ~${market_price:.2f}\nTP: ${tp_price:.2f} SL: ${sl_price:.2f}", 
                         priority=0)

    except Exception as e:
        logger.exception(f"Failed to open {position_type} position")
        send_notification(f"ERROR opening {position_type} position", str(e), priority=1)


def main():
    """
    Main trading loop.
    """
    logger.info(f"🚀 Starting HyperLiquid {SYMBOL}/USD trading bot with {LEVERAGE}x leverage...")
    
    # --- Fetch asset metadata once at startup ---
    try:
        meta = info.meta()
        
        # Find the asset's info dictionary in the universe list
        asset_info = next((item for item in meta["universe"] if item["name"] == SYMBOL), None)
        
        if asset_info is None:
            logger.error(f"Could not find asset info for {SYMBOL} in metadata.")
            sys.exit(1)
        
        # Use .get() to safely access 'tickSize' and provide a default
        tick_size_str = asset_info.get("tickSize")
        if tick_size_str:
            tick_size = Decimal(tick_size_str)
            logger.info(f"✅ Successfully fetched tick size for {SYMBOL}: {tick_size}")
        else:
            # Based on the error "Price must be divisible by tick size. asset=1", the tick size is likely 1.
            # We will use this as a fallback if the API does not provide the value.
            tick_size = Decimal("1")
            logger.warning(f"Could not find 'tickSize' for {SYMBOL} in API response. Using default: {tick_size} based on API error feedback.")
            logger.warning(f"Available keys in asset_info for {SYMBOL}: {list(asset_info.keys())}")

    except Exception as e:
        logger.exception("An unexpected error occurred while fetching asset metadata")
        sys.exit(1)

    set_leverage(SYMBOL, LEVERAGE)
    
    try:
        while True:
            try:
                # Check if we have an open position
                current_size, entry_price = get_current_position()
                
                if current_size != Decimal("0"):
                    logger.debug(f"Current position: {current_size} {SYMBOL} @ ${entry_price}")
                    # Skip trading if we already have a position
                    time.sleep(POLL_SECS)
                    continue
                
                # No position, get trading decision from Grok
                logger.info("No current position. Getting trading decision from Grok...")
                result = build_and_run_trading_graph()
                
                if not result or "decision" not in result:
                    logger.warning("No valid decision from Grok trading graph. Skipping.")
                    time.sleep(POLL_SECS)
                    continue
                
                decision = result["decision"]
                reason = result.get("reason", "No reason provided")
                analysis = result.get("analysis", "No analysis")
                
                logger.info(f"Grok decision: {decision.upper()} - {reason}")
                
                # Get account value to determine position size
                account_value = get_account_value()
                if account_value <= Decimal("10"):
                    logger.warning(f"Account value too small (${account_value:.2f}), skipping.")
                    time.sleep(POLL_SECS)
                    continue
                
                # Open position based on decision
                if decision.lower() == "long":
                    open_position(is_long=True, size_usd=account_value, tick_size=tick_size)
                elif decision.lower() == "short":
                    open_position(is_long=False, size_usd=account_value, tick_size=tick_size)
                else:
                    logger.warning(f"Unknown decision: {decision}. Expected 'long' or 'short'.")
                
            except Exception as e:
                logger.exception("Error in trading loop")
                send_notification("ERROR in trading loop", str(e), priority=1)
            
            time.sleep(POLL_SECS)
            
    except KeyboardInterrupt:
        logger.info("\nInterrupted by user, shutting down...")
        sys.exit(0)
    except Exception as e:
        logger.exception("An unexpected error occurred in the main loop.")
        send_notification("FATAL BOT ERROR", str(e), priority=2)


if __name__ == "__main__":
    main()
