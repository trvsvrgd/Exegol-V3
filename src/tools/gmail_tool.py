import os
import base64
from email.message import EmailMessage
from typing import Optional

def send_gmail_message(to: str, subject: str, body: str, body_html: Optional[str] = None) -> str:
    """Sends an email via the Gmail API.
    
    Setup:
    1. Enable Gmail API in Google Cloud Console.
    2. Download `credentials.json`.
    3. Run a local script to generate `token.json` (OAuth2 flow).
    4. Place `token.json` in the root directory (or set GMAIL_TOKEN_PATH).

    Fallback: Mocks the send if dependencies or credentials are missing.
    """
    try:
        from google.oauth2.credentials import Credentials
        from googleapiclient.discovery import build
        
        token_path = os.getenv("GMAIL_TOKEN_PATH", "token.json")
        
        if not os.path.exists(token_path):
            mode = "HTML" if body_html else "TEXT"
            return f"[MOCK GMAIL] {mode} To: {to} | Sub: {subject} | Body: {body[:100]}..."
            
        creds = Credentials.from_authorized_user_file(token_path)
        service = build('gmail', 'v1', credentials=creds)
        
        message = EmailMessage()
        message.set_content(body) # Plain text version
        
        if body_html:
            message.add_alternative(body_html, subtype='html')
            
        message['To'] = to
        message['From'] = 'me'
        message['Subject'] = subject
        
        encoded_message = base64.urlsafe_b64encode(message.as_bytes()).decode()
        create_message = {'raw': encoded_message}
        
        send_message = (service.users().messages().send(userId="me", body=create_message).execute())
        return f"Success: Sent message with ID {send_message['id']}"
        
    except ImportError:
        return "Error: google-api-python-client or google-auth not installed."
    except Exception as e:
        return f"Error: {str(e)}"
