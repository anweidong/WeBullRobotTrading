import time
import os
from alpaca.trading.client import TradingClient
from alpaca.trading.requests import MarketOrderRequest
from alpaca.trading.enums import OrderSide, TimeInForce
from alpaca.data.historical import StockHistoricalDataClient
from alpaca.data.requests import StockLatestQuoteRequest

# Constants
INVEST_PERCENTAGE = 0.9  # 90% of available balance
API_KEY = os.getenv('ALPACA_API_KEY')
API_SECRET = os.getenv('ALPACA_API_SECRET')

POLLING_FREQUENCY = 0.1  # sec

# Initialize Alpaca clients
trading_client = TradingClient(API_KEY, API_SECRET, paper=True)
data_client = StockHistoricalDataClient(API_KEY, API_SECRET)

def get_us_balance():
    """Fetch paper account balance"""
    account = trading_client.get_account()
    return float(account.cash)

def get_current_price(symbol):
    """Get real-time price using latest quote"""
    request = StockLatestQuoteRequest(symbol_or_symbols=[symbol])
    quotes = data_client.get_stock_latest_quote(request)
    return float(quotes[symbol].ask_price)

def place_us_order(symbol, qty, side):
    """Place a market order"""
    if qty < 0.01:  # Minimum quantity of 0.01 shares
        return False

    # Create market order
    order_details = MarketOrderRequest(
        symbol=symbol,
        qty=qty,
        side=OrderSide.BUY if side == 'BUY' else OrderSide.SELL,
        time_in_force=TimeInForce.DAY
    )

    try:
        order = trading_client.submit_order(order_details)
        print(f"Order placed: {order}")
        return True
    except Exception as e:
        print(f"Error placing order: {e}")
        return False

def get_position_quantity(symbol):
    """Get quantity of shares held for a symbol"""
    try:
        position = trading_client.get_open_position(symbol)
        return float(position.qty)
    except:
        return 0

def main():
    try:
        while True:
            signal_type, symbol = check_signal()  # Implement your signal logic
            if signal_type is None:
                time.sleep(POLLING_FREQUENCY)
            
            current_balance = get_us_balance()
            current_price = get_current_price(symbol)
            
            if signal_type == 'BUY' and current_balance > 0:
                invest_amt = current_balance * INVEST_PERCENTAGE
                qty = round(invest_amt / current_price, 2)  # Allow fractional shares with 2 decimal points
                if qty > 0:
                    print(f"Buying {qty} shares of {symbol} at ${current_price:.2f}")
                    place_us_order(symbol, qty, 'BUY')
                
            elif signal_type == 'SELL':
                qty = get_position_quantity(symbol)
                if qty > 0:
                    print(f"Selling {qty} shares of {symbol}")
                    place_us_order(symbol, qty, 'SELL')
            
            time.sleep(POLLING_FREQUENCY)  # Reduce polling frequency

    except KeyboardInterrupt:
        print("\nStopping trading bot...")


if __name__ == "__main__":
    print(get_us_balance())
