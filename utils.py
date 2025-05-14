import os
from gmail_reader import process_messages

# Global set to track processed messages across function calls
processed_gmail_message = set()

def check_signal():
    """
    Check for trading signals in Gmail messages.
    Returns: (signal_type, symbol)
    signal_type: "BUY", "SELL", "SHORT", or "COVER"
    symbol: The trading symbol (e.g. "ETH", "TSM", etc.)
    """
    messages = process_messages()[::-1]  # Get all messages within 2 minutes
    robot_name = os.getenv("ROBOT_NAME")
    global processed_gmail_message

    for msg in messages:
        if msg['id'] in processed_gmail_message:
            continue
        
        # Clean message body by removing extra spaces and newlines
        cleaned_body = ' '.join(msg["body"].strip().splitlines())
        if robot_name in cleaned_body:
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
