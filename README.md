# Gmail Label Reader

This Python script provides functionality to read Gmail messages with specific labels and mark them as read.

## Setup Instructions

1. Set up a Google Cloud Project and enable the Gmail API:
   - Go to the [Google Cloud Console](https://console.cloud.google.com/)
   - Create a new project or select an existing one
   - Enable the Gmail API for your project
   - Go to Credentials
   - Create OAuth 2.0 Client ID credentials
   - Download the client configuration file and save it as `credentials.json` in the project directory

2. Install the required dependencies:
```bash
pip install -r requirements.txt
```

3. Update the `LABEL_NAME` variable in `gmail_reader.py` with your desired Gmail label name.

4. Run the script:
```bash
python gmail_reader.py
```

On first run, the script will open a browser window for OAuth authentication. After authenticating, the credentials will be saved locally in `token.pickle` for future use.

## Features

- Authenticates with Gmail API using OAuth 2.0
- Retrieves messages with a specific label
- Reads message content (subject and body)
- Marks messages as read
- Handles both plain text and multipart messages

## Functions

- `get_gmail_service()`: Creates and returns an authenticated Gmail API service instance
- `get_messages_by_label(service, label_name, max_results=10)`: Retrieves messages with the specified label
- `read_message(service, msg_id)`: Reads and returns the content of a specific message
- `mark_as_read(service, msg_id)`: Marks a message as read
- `process_unread_messages(label_name, max_messages=10)`: Main function to process unread messages with a specific label

## Error Handling

The script includes error handling for common issues:
- Invalid credentials
- Label not found
- Message reading errors
- API errors

## Security Note

The script requires the following Gmail API scope:
- `https://www.googleapis.com/auth/gmail.modify` (Allows reading and modifying but not deleting messages)

Credentials are stored locally in `token.pickle` and should be kept secure.
