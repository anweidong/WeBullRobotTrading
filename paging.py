import requests
from datetime import datetime
import logging
from logging.handlers import TimedRotatingFileHandler

# Configure logging
logger = logging.getLogger('paging')
logger.setLevel(logging.INFO)
formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')

# File handler with daily rotation
file_handler = TimedRotatingFileHandler(
    'log/paging.log',
    when='midnight',
    interval=1,
    backupCount=30  # Keep logs for 30 days
)
file_handler.setFormatter(formatter)
logger.addHandler(file_handler)

# Read the credentials from the file
with open('credentials.txt', 'r') as file:
    file.readline().strip()  # Skip email
    file.readline().strip()  # Skip password
    api_key = file.readline().strip()
url = "https://api.prowlapp.com/publicapi/add"


def send_notification(title: str, decription: str, priority=2):
    """
    https://www.prowlapp.com/api.php
    """
    data = {
        "apikey": api_key,
        "application": "Python App",
        "event": title,
        "description": decription,
        "priority": priority
    }
    response = requests.post(url, data=data)
    logger.info(response.text)
    logger.info(f"Notification sent on {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}!")

if __name__ == "__main__":
    send_notification("abc", "def", priority=-1)
