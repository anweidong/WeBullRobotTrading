# WeBull Robot Trading

An automated trading bot that monitors Gmail for WeBull trading signals and executes trades automatically through Alpaca Markets.

## Features

- Monitors Gmail for specific trading signals from WeBull
- Automatically executes trades on Alpaca Markets based on signals
- Supports both BUY and SELL orders
- Real-time price quotes through Alpaca Data API
- Fractional share trading support
- Hourly status notifications
- Comprehensive logging system

## Prerequisites

- Alpaca Markets account with API access
- Google Cloud Project with Gmail API enabled
- Python 3.x

## Setup Instructions

1. Set up environment variables:
   ```bash
   ALPACA_API_KEY=your_alpaca_api_key
   ALPACA_API_SECRET=your_alpaca_secret_key
   ROBOT_NAME="Day Trader: Price Action Bot for High Volatility and High Liquidity Stocks (TA)"
   ```

2. Set up Google Cloud Project and Gmail API:
   - Go to the [Google Cloud Console](https://console.cloud.google.com/)
   - Create a new project or select an existing one
   - Enable the Gmail API for your project
   - Create OAuth 2.0 Client ID credentials
   - Download the client configuration file and save it as `credentials.json` in the project directory

3. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```

4. Run the trading bot:
   ```bash
   ./start_trading.sh
   ```

## How It Works

1. The bot continuously monitors a Gmail account for trading signals
2. When a signal is detected:
   - For BUY signals: Invests 95% of available balance in the specified stock
   - For SELL signals: Sells entire position of the specified stock
3. Trades are executed as market orders through Alpaca
4. Notifications are sent for each trade execution and hourly status updates

## Configuration

- `POLLING_FREQUENCY`: Time between Gmail checks (default: 1 second)
- `INVEST_PERCENTAGE`: Percentage of available balance to invest (default: 95%)
- Trading is performed on live Alpaca account (paper=False)

## Security

- Gmail API requires OAuth 2.0 authentication
- Credentials are stored locally in `token.pickle`
- Alpaca API keys should be kept secure and not committed to version control

## Error Handling

The bot includes comprehensive error handling for:
- API connection issues
- Trade execution failures
- Invalid signals
- Account balance issues

## Logging

All activities are logged with timestamps and detailed information:
- Trade executions
- Signal detections
- Errors and exceptions
- Hourly status updates

## Dependencies

- google-auth-oauthlib: Gmail API authentication
- google-auth-httplib2: HTTP client for Gmail API
- google-api-python-client: Gmail API client
- alpaca-py: Alpaca Markets trading API
- pytz: Timezone support
- python-dotenv: Environment variable management
