#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Hyperliquid ETH/USD Perpetual Futures Bot using Hyperliquid Python SDK

This bot listens for BUY/SELL signals via `check_signal()` and opens or closes
ETH perpetual futures on Hyperliquid using the official Python SDK for all
exchange interactions.

Dependencies:
    pip install --upgrade hyperliquid-python-sdk eth-account python-dotenv web3

Environment variables (.env):
  HL_SIGNING_KEY    = your API wallet signing key (hex string, 32-byte)
  HL_PUBLIC_KEY     = your main Hyperliquid account address (0x...)
  POLLING_FREQUENCY = seconds between signal polls (default 5)
  LEVERAGE          = leverage for trades (default 20)
"""
import os
import sys
import time
import logging
import json
from decimal import Decimal, ROUND_DOWN, ROUND_UP
from collections import deque
from dotenv import load_dotenv

from eth_account import Account
from hyperliquid.info import Info
from hyperliquid.exchange import Exchange
from hyperliquid.utils import constants

# These would be in your local utility files
from utils import check_signal
from paging import send_notification

# Load environment variables from .env file
load_dotenv()

# --- Configuration ---
SIGNING_KEY_HEX = os.getenv("HL_SIGNING_KEY")
MASTER_WALLET = os.getenv("HL_PUBLIC_KEY")
POLL_SECS = int(os.getenv("POLLING_FREQUENCY", "5"))
LEVERAGE = int(os.getenv("LEVERAGE", "20"))
SYMBOL = "ETH"
NUM_PARTS = 10  # Split account value into 10 equal parts for trading

# Logging setup
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s | %(levelname)-8s | %(message)s"
)
# Suppress noisy INFO logs from dependency libraries
logging.getLogger('oauth2client').setLevel(logging.WARNING)
logging.getLogger('googleapiclient.discovery_cache').setLevel(logging.ERROR)
logger = logging.getLogger("hl-bot")

# --- Global State ---
# Track open positions: list of (entry_price, size_eth)
trade_queue = deque()

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


def calculate_trade_size(account_value: Decimal) -> Decimal:
    """
    Calculate the USD value for a new trade based on remaining slots.
    """
    remaining_slots = NUM_PARTS - len(trade_queue)
    if remaining_slots <= 0:
        return Decimal("0")
    return (account_value / remaining_slots).quantize(Decimal("0.01"), rounding=ROUND_DOWN)


def round_to_tick_size(price: Decimal, tick_size: Decimal, rounding=ROUND_DOWN) -> Decimal:
    """
    Rounds a price to the nearest valid tick size.
    """
    return (price / tick_size).quantize(Decimal("1"), rounding=rounding) * tick_size


def open_long(size_usd: Decimal, tick_size: Decimal):
    """
    Open a long position by placing an aggressive IOC limit buy order using the SDK.
    """
    try:
        price = get_market_price()
        size_eth = (size_usd * LEVERAGE / price).quantize(Decimal("0.0001"), rounding=ROUND_DOWN)

        min_size = Decimal("0.001")
        if size_eth < min_size:
            raise ValueError(f"Order size {size_eth} ETH is below minimum {min_size} ETH")

        logger.info(f"Calculated order: {size_eth:.4f} ETH (${size_usd:.2f} @ ${price:.2f})")
        
        # Calculate an aggressive price 5% above market
        raw_limit_price = price * Decimal("1.05")
        # Round the price UP to the nearest tick size to ensure it's aggressive
        limit_price = round_to_tick_size(raw_limit_price, tick_size, rounding=ROUND_UP)
        
        logger.info(f"Using aggressive limit buy price: ${limit_price} (Tick Size: {tick_size})")

        order_type = {"limit": {"tif": "Ioc"}}
        resp = exchange.order(
            SYMBOL,
            True,  # is_buy
            float(size_eth),
            float(limit_price),
            order_type
        )
        logger.debug(f"Order response: {resp}")

        # Check for both top-level and nested errors
        if resp["status"] == "ok":
            statuses = resp.get("response", {}).get("data", {}).get("statuses", [])
            for status in statuses:
                if "error" in status:
                    raise ValueError(f"Order failed: {status['error']}")
        else:
            raise ValueError(f"Order request failed: {resp}")

        trade_queue.append((price, size_eth))
        logger.info(f"✅ BUY {size_eth:.4f} {SYMBOL} @ market price ~${price:.2f}")
        send_notification("BUY", f"Opened {size_eth:.4f} {SYMBOL} @ ~${price:.2f}", priority=0)

    except Exception as e:
        logger.exception("Failed to open long position")
        send_notification("ERROR opening long", str(e), priority=1)


def close_oldest_position(tick_size: Decimal):
    """
    Close the oldest open position by placing an aggressive IOC limit sell order using the SDK.
    """
    if not trade_queue:
        logger.debug("No positions to close.")
        return

    entry_price, size_eth = trade_queue.popleft()
    try:
        price = get_market_price()
        
        # Calculate an aggressive price 5% below market
        raw_limit_price = price * Decimal("0.95")
        # Round the price DOWN to the nearest tick size to ensure it's aggressive
        limit_price = round_to_tick_size(raw_limit_price, tick_size, rounding=ROUND_DOWN)

        logger.info(f"Using aggressive limit sell price: ${limit_price} (Tick Size: {tick_size})")
        
        order_type = {"limit": {"tif": "Ioc"}}
        resp = exchange.order(
            SYMBOL,
            False,  # is_buy
            float(size_eth),
            float(limit_price),
            order_type
        )
        logger.debug(f"Order response: {resp}")

        # Check for both top-level and nested errors
        if resp["status"] == "ok":
            statuses = resp.get("response", {}).get("data", {}).get("statuses", [])
            for status in statuses:
                if "error" in status:
                    # If closing fails, add the position back to the queue to retry
                    trade_queue.appendleft((entry_price, size_eth))
                    raise ValueError(f"Order failed: {status['error']}")
        else:
            # If closing fails, add the position back to the queue to retry
            trade_queue.appendleft((entry_price, size_eth))
            raise ValueError(f"Order request failed: {resp}")
        
        pnl_usd = (price - entry_price) * size_eth
        logger.info(f"✅ SELL {size_eth:.4f} {SYMBOL} @ ${price:.2f}, PnL: ${pnl_usd:.2f}")
        send_notification("SELL", f"Closed {size_eth:.4f} {SYMBOL}, PnL: ${pnl_usd:.2f}", priority=0)

    except Exception as e:
        logger.exception("Failed to close position")
        send_notification("ERROR closing position", str(e), priority=1)
        # Ensure the failed trade is returned to the queue if it was already removed
        if (entry_price, size_eth) not in trade_queue:
            trade_queue.appendleft((entry_price, size_eth))


def main():
    """
    Main trading loop.
    """
    logger.info("🚀 Starting Hyperliquid ETH/USD trading bot...")
    
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
                signal_type, asset = check_signal() 
            except Exception as sig_err:
                logger.error(f"Signal check error: {sig_err}")
                time.sleep(POLL_SECS)
                continue
            
            if asset != f"{SYMBOL}.X":
                time.sleep(POLL_SECS)
                continue

            if signal_type == "BUY":
                if len(trade_queue) >= NUM_PARTS:
                    logger.warning("Max open positions reached. No new positions will be opened.")
                else:
                    account_value = get_account_value()
                    size_usd = calculate_trade_size(account_value)
                    if size_usd <= Decimal("1"):
                        logger.warning(f"Trade size too small (${size_usd:.2f}), skipping.")
                    else:
                        open_long(size_usd, tick_size)

            elif signal_type == "SELL":
                close_oldest_position(tick_size)

            time.sleep(POLL_SECS)
            
    except KeyboardInterrupt:
        logger.info("\nInterrupted by user, shutting down...")
        sys.exit(0)
    except Exception as e:
        logger.exception("An unexpected error occurred in the main loop.")
        send_notification("FATAL BOT ERROR", str(e), priority=2)


if __name__ == "__main__":
    main()
