import requests
from datetime import datetime


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
    "description":decription,
    "priority": priority
    }
    response = requests.post(url, data=data)
    print(response.text)
    print(f"Notification sent on {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}!")

if __name__ == "__main__":
    send_notification("abc", "def", priority=-1)