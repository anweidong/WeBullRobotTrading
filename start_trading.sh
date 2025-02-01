#!/bin/bash

# Set Alpaca API credentials as environment variables
# Please replace these placeholder values with your actual Alpaca API credentials
export ALPACA_API_KEY=""
export ALPACA_API_SECRET=""

export ROBOT_NAME="Day Trader: Price Action Bot for High Volatility and High Liquidity Stocks (TA)"

# Start the trading script
python3 trading.py
