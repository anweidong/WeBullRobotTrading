import time
import os
from alpaca.trading.client import TradingClient
from paging import send_notification
from alpaca.trading.requests import MarketOrderRequest
from alpaca.trading.enums import OrderSide, TimeInForce
from alpaca.data.historical import StockHistoricalDataClient
from alpaca.data.requests import StockLatestQuoteRequest
from gmail_reader import process_messages
from logger import get_logger

logger = get_logger(__name__)

# Constants
MAX_CONCURRENT_SYMBOLS = 9  # Maximum number of concurrent active trading symbols
INVEST_PERCENTAGE = 0.99 / MAX_CONCURRENT_SYMBOLS
API_KEY = os.getenv('ALPACA_API_KEY')
API_SECRET = os.getenv('ALPACA_API_SECRET')
ROBOT_NAME = os.getenv("ROBOT_NAME")
SHORT_ENABLED = os.getenv('SHORT_ENABLED', 'true').lower() == 'true'

POLLING_FREQUENCY = 0.5  # sec

processed_gmail_message = set()
active_trading_symbols = {"TSM", "NVDS", "DUG", "NVDA"}  # Track which stocks we're currently trading
initial_cash = 25000  # Store initial cash balance when we start trading

# Initialize Alpaca clients
trading_client = TradingClient(API_KEY, API_SECRET, paper=False)
data_client = StockHistoricalDataClient(API_KEY, API_SECRET)

def get_us_balance():
    """Fetch account cash"""
    account = trading_client.get_account()
    return float(account.cash)

def get_current_price(symbol):
    """Get real-time price using latest quote"""
    request = StockLatestQuoteRequest(symbol_or_symbols=[symbol])
    quotes = data_client.get_stock_latest_quote(request)
    ask_price = float(quotes[symbol].ask_price)
    # If ask_price is 0, use bid_price instead
    if ask_price == 0:
        return float(quotes[symbol].bid_price)
    return ask_price

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
        logger.info(f"Order placed: {order}")
        return True
    except Exception as e:
        logger.error(f"Error placing order: {e}")
        raise e
        return False

def get_position_quantity(symbol):
    """Get quantity of shares held for a symbol"""
    try:
        position = trading_client.get_open_position(symbol)
        return float(position.qty)
    except:
        return 0

def can_trade_symbol(symbol, signal_type):
    """Check if we can trade this symbol"""
    global active_trading_symbols

    # For closing positions (SELL/COVER), only allow if it's in our active symbols
    # and we have a position
    if signal_type in ['SELL', 'COVER']:
        position_qty = get_position_quantity(symbol)
        return symbol in active_trading_symbols and position_qty != 0
    
    # Check account status for day trading restrictions
    account = trading_client.get_account()
    equity = float(account.equity)
    daytrading_buying_power = float(account.daytrading_buying_power)
    
    # If equity is less than 25000 and daytrading_buying_power is zero, cannot trade
    # https://www.finra.org/investors/investing/investment-products/stocks/day-trading
    # if equity < 25000 and daytrading_buying_power == 0:
    #     logger.warning(f"Cannot trade: equity (${equity:.2f}) < $25000 and no daytrading buying power")
    #     send_notification("Trading Restricted", 
    #                     f"Cannot trade {symbol}: Account equity (${equity:.2f}) below $25,000 and no daytrading buying power", 
    #                     priority=0)
    #     return False
    
    # For new positions (BUY/SHORT), only allow if we haven't reached max concurrent symbols
    if signal_type in ['BUY', 'SHORT']:
        if len(active_trading_symbols) < MAX_CONCURRENT_SYMBOLS:
            return True
        return False
    
    return False

def has_pending_orders():
    """Check if there are any pending orders"""
    try:
        orders = trading_client.get_orders()
        return len(orders) > 0
    except Exception as e:
        logger.error(f"Error checking pending orders: {e}")
        return False
    
def check_signal():
    messages = process_messages()[::-1]  # Get all messages within 2 minutes
    global processed_gmail_message
    for msg in messages:
        if msg['id'] in processed_gmail_message:
            continue
        
        # Clean message body by removing extra spaces and newlines
        cleaned_body = ' '.join(msg["body"].strip().splitlines())
        if ROBOT_NAME in cleaned_body:
            message = cleaned_body.lower()
            
            # Check for buy signal
            if "bought" in message and "at" in message:
                # Extract symbol - assuming format "bought X SYMBOL shares at"
                words = message.split()
                for i, word in enumerate(words):
                    if word == "bought":
                        symbol = words[i + 2].upper()  # Get the word after the quantity
                        processed_gmail_message.add(msg['id'])
                        return "BUY", symbol
            
            # Check for sell signal
            elif "sold to close" in message and "at" in message:
                # Extract symbol - assuming format "sold to close X SYMBOL shares at"
                words = message.split()
                for i, word in enumerate(words):
                    if word == "close":
                        symbol = words[i + 2].upper()  # Get the word after the quantity
                        processed_gmail_message.add(msg['id'])
                        return "SELL", symbol

            # Check for short signal
            elif "shorted" in message and "at" in message:
                # Extract symbol - assuming format "shorted X SYMBOL shares at"
                words = message.split()
                for i, word in enumerate(words):
                    if word == "shorted":
                        symbol = words[i + 2].upper()  # Get the word after the quantity
                        processed_gmail_message.add(msg['id'])
                        return "SHORT", symbol

            # Check for cover signal
            elif "covered to close" in message and "at" in message:
                # Extract symbol - assuming format "covered to close X SYMBOL shares at"
                words = message.split()
                for i, word in enumerate(words):
                    if word == "close":
                        symbol = words[i + 2].upper()  # Get the word after the quantity
                        processed_gmail_message.add(msg['id'])
                        return "COVER", symbol
            
            # Mark message as processed even if it doesn't contain a valid signal
            processed_gmail_message.add(msg['id'])
    
    return None, None


def main():
    try:
        logger.info("Starting trading bot...")
        global active_trading_symbols, initial_cash
        while True:
            try:
                signal_type, symbol = check_signal()
                if signal_type is None:
                    time.sleep(POLLING_FREQUENCY)
                    continue

                # Check if shorting is enabled for SHORT and COVER operations
                if signal_type in ['SHORT', 'COVER'] and not SHORT_ENABLED:
                    logger.warning(f"Skipping {signal_type} signal for {symbol} - shorting is disabled")
                    send_notification("Order Rejected", f"Cannot {signal_type} {symbol} - shorting is disabled", priority=0)
                    time.sleep(POLLING_FREQUENCY)
                    continue
                
                current_balance = get_us_balance()
                
                # Store initial cash when we start trading first symbol
                if len(active_trading_symbols) == 0:
                    initial_cash = current_balance
                
                current_price = get_current_price(symbol)
                
                # Check if we can trade this symbol
                if signal_type and not can_trade_symbol(symbol, signal_type):
                    # Note: Notification is now handled inside can_trade_symbol for equity/daytrading restrictions
                    # Only send max symbols notification here
                    if len(active_trading_symbols) >= MAX_CONCURRENT_SYMBOLS:
                        logger.warning(f"Skipping {signal_type} signal for {symbol} - already trading {len(active_trading_symbols)} symbols: {', '.join(active_trading_symbols)}")
                        send_notification("Order Rejected", f"Cannot trade {symbol} - already trading maximum allowed symbols: {', '.join(active_trading_symbols)}", priority=0)
                    else:
                        logger.warning(f"Skipping {signal_type} signal for {symbol} - not actively trading or account has no position")
                        send_notification("Order Rejected", f"Cannot trade {symbol} - not actively trading or account has no position", priority=0)
                    time.sleep(POLLING_FREQUENCY)
                    continue

                # Check for pending orders
                if signal_type and has_pending_orders():
                    logger.warning(f"Skipping {signal_type} signal for {symbol} - there is already a pending order")
                    send_notification("Order Rejected", f"Cannot place {signal_type} order for {symbol} - there is already a pending order", priority=0)
                    time.sleep(POLLING_FREQUENCY)
                    continue

                if signal_type == 'BUY' and current_balance > 0:
                    # Use initial cash for investment calculation
                    invest_amt = initial_cash * INVEST_PERCENTAGE
                    # But ensure we don't exceed available cash
                    invest_amt = min(invest_amt, current_balance)
                    qty = int(invest_amt / current_price)
                    if qty > 0:
                        logger.info(f"Buying {qty} shares of {symbol} at ${current_price:.2f}")
                        if place_us_order(symbol, qty, 'BUY'):
                            send_notification("BUY Signal", f"Bought {qty} shares of {symbol} at ${current_price:.2f}", priority=0)
                            # Add to active symbols since we've opened a position
                            active_trading_symbols.add(symbol)
                
                elif signal_type == 'SELL':
                    qty = get_position_quantity(symbol)
                    if qty > 0:
                        logger.info(f"Selling {qty} shares of {symbol}")
                        if place_us_order(symbol, qty, 'SELL'):
                            send_notification("SELL Signal", f"Sold {qty} shares of {symbol} at ${current_price:.2f}", priority=0)
                            # Remove from active symbols since we've closed the position
                            active_trading_symbols.discard(symbol)
                            # Reset initial cash if no more active symbols
                            if len(active_trading_symbols) == 0:
                                initial_cash = None
                    else:
                        logger.warning(f"No {symbol} available while trying to sell")
                        send_notification("Nothing to sell", f"No {symbol} available while trying to sell", priority=0)

                elif signal_type == 'SHORT':
                    # Use initial cash for investment calculation
                    invest_amt = initial_cash * INVEST_PERCENTAGE
                    # But ensure we don't exceed available cash
                    invest_amt = min(invest_amt, current_balance)
                    qty = int(invest_amt / current_price)  # No fractional shares for SHORT
                    if qty > 0:
                        logger.info(f"Shorting {qty} whole shares of {symbol} at ${current_price:.2f}")
                        if place_us_order(symbol, qty, 'SELL'):  # Short is a SELL order
                            send_notification("SHORT Signal", f"Shorted {qty} shares of {symbol} at ${current_price:.2f}", priority=0)
                            # Add to active symbols since we've opened a short position
                            active_trading_symbols.add(symbol)

                elif signal_type == 'COVER':
                    qty = abs(get_position_quantity(symbol))  # Get absolute value of short position
                    if qty > 0:
                        logger.info(f"Covering {qty} shares of {symbol}")
                        if place_us_order(symbol, qty, 'BUY'):  # Cover is a BUY order
                            send_notification("COVER Signal", f"Covered {qty} shares of {symbol} at ${current_price:.2f}", priority=0)
                            # Remove from active symbols since we've closed the position
                            active_trading_symbols.discard(symbol)
                            # Reset initial cash if no more active symbols
                            if len(active_trading_symbols) == 0:
                                initial_cash = None
                    else:
                        logger.warning(f"No {symbol} short position available to cover")
                        send_notification("Nothing to cover", f"No {symbol} short position available to cover", priority=0)
                
                time.sleep(POLLING_FREQUENCY)
            except Exception as e:
                logger.error(f"Error while trading {e}")
                send_notification("ERROR Trading", f"Error while trading {e}")
                time.sleep(POLLING_FREQUENCY)

    except KeyboardInterrupt:
        logger.info("Stopping trading bot...")


if __name__ == "__main__":
    main()
