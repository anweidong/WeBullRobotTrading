from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from googleapiclient.discovery import build
import os.path
import pickle
import base64
from email.message import EmailMessage
from datetime import datetime
import pytz

# If modifying these scopes, delete the file token.pickle.
SCOPES = ['https://www.googleapis.com/auth/gmail.modify']

def get_gmail_service():
    """Gets Gmail API service instance.
    
    Returns:
        service: Gmail API service instance
    """
    creds = None
    # The file token.pickle stores the user's access and refresh tokens
    if os.path.exists('token.pickle'):
        with open('token.pickle', 'rb') as token:
            creds = pickle.load(token)
            
    # If there are no (valid) credentials available, let the user log in.
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(
                'credentials.json', SCOPES)
            creds = flow.run_local_server(port=0)
            
        # Save the credentials for the next run
        with open('token.pickle', 'wb') as token:
            pickle.dump(creds, token)

    return build('gmail', 'v1', credentials=creds)

def get_messages_by_label(service, label_name, max_results=10):
    """Gets messages with specified label.
    
    Args:
        service: Gmail API service instance
        label_name: Name of the Gmail label to filter by
        max_results: Maximum number of messages to return
        
    Returns:
        list: List of message objects
    """
    try:
        # First get the label ID for the given label name
        results = service.users().labels().list(userId='me').execute()
        labels = results.get('labels', [])
        
        label_id = None
        for label in labels:
            if label['name'].lower() == label_name.lower():
                label_id = label['id']
                break
                
        if not label_id:
            raise ValueError(f"Label '{label_name}' not found")
            
        # Get messages with this label
        results = service.users().messages().list(
            userId='me',
            labelIds=[label_id],
            maxResults=max_results
        ).execute()
        
        messages = results.get('messages', [])
        return messages
        
    except Exception as e:
        print(f"An error occurred: {e}")
        return []

def is_message_within_one_minute(message_date):
    """Check if the message is from within the last minute in PDT timezone.
    
    Args:
        message_date: datetime object of the message
        
    Returns:
        bool: True if message is from within the last minute, False otherwise
    """
    pdt_tz = pytz.timezone('America/Los_Angeles')
    now = datetime.now(pdt_tz)
    message_date_pdt = message_date.astimezone(pdt_tz)
    
    time_difference = now - message_date_pdt
    return time_difference.total_seconds() <= 120

def read_message(service, msg_id):
    """Reads a specific message and returns its content.
    
    Args:
        service: Gmail API service instance
        msg_id: ID of the message to read
        
    Returns:
        dict: Message content including subject and body
    """
    try:
        # Get the message
        message = service.users().messages().get(
            userId='me',
            id=msg_id,
            format='full'
        ).execute()
        
        headers = message['payload']['headers']
        subject = ''
        for header in headers:
            if header['name'].lower() == 'subject':
                subject = header['value']
                break
                
        # Get the message body
        body = ''
        
        def get_body_from_part(part):
            """Recursively extract text from message part."""
            if part.get('mimeType') == 'text/plain' and 'data' in part.get('body', {}):
                return base64.urlsafe_b64decode(part['body']['data']).decode('utf-8')
            elif part.get('mimeType') == 'text/html' and 'data' in part.get('body', {}):
                # Only use HTML if we haven't found plain text
                if not body:
                    return base64.urlsafe_b64decode(part['body']['data']).decode('utf-8')
            elif 'parts' in part:
                # Recursively check parts
                for subpart in part['parts']:
                    text = get_body_from_part(subpart)
                    if text:
                        return text
            return None

        if 'parts' in message['payload']:
            # Handle multipart messages
            for part in message['payload']['parts']:
                text = get_body_from_part(part)
                if text:
                    body = text
                    break
        elif 'body' in message['payload'] and 'data' in message['payload']['body']:
            # Handle single part messages
            body = base64.urlsafe_b64decode(message['payload']['body']['data']).decode('utf-8')
        
        if not body:
            print(f"Warning: Could not extract body from message {msg_id}")
            
        # Get message date from headers
        date_str = ''
        for header in headers:
            if header['name'].lower() == 'date':
                date_str = header['value']
                break
        
        # Parse the email date with more robust handling
        try:
            # Clean up the date string
            clean_date = date_str.replace(' (UTC)', '')  # Remove (UTC) suffix if present
            
            try:
                # Try parsing with timezone offset
                message_date = datetime.strptime(clean_date, '%a, %d %b %Y %H:%M:%S %z')
            except ValueError:
                # If no timezone info, assume UTC
                message_date = datetime.strptime(clean_date, '%a, %d %b %Y %H:%M:%S')
                message_date = pytz.UTC.localize(message_date)
        except Exception as e:
            print(f"Error parsing date '{date_str}': {e}")
            return None
        
        return {
            'id': msg_id,
            'subject': subject,
            'body': body,
            'labels': message['labelIds'],
            'date': message_date
        }
        
    except Exception as e:
        print(f"An error occurred while reading message: {e}")
        return None


def process_messages(label_name, max_messages=10):
    """Main function to process messages with a specific label.
    
    Args:
        label_name: Name of the Gmail label to process
        max_messages: Maximum number of messages to process
    
    Returns:
        list: List of processed message contents
    """
    service = get_gmail_service()
    messages = get_messages_by_label(service, label_name, max_messages)
    processed_messages = []
    
    for message in messages:
        # Read the message
        msg_content = read_message(service, message['id'])
        if msg_content and is_message_within_one_minute(msg_content['date']):
            processed_messages.append(msg_content)
                
    return processed_messages

# Example usage:
if __name__ == "__main__":
    # Replace with your desired label
    LABEL_NAME = "Tickeron"
    messages = process_messages(LABEL_NAME)
    
    for msg in messages:
        print(msg)
        print(f"\nSubject: {msg['subject']}")
        print(f"Body: {msg['body'][:200]}...")  # Print first 200 chars of body
