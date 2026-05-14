import os
import base64
import json
from email.message import EmailMessage
from typing import Optional

def send_gmail_message(to: str, subject: str, body: str, body_html: Optional[str] = None) -> str:
    """Sends an email via the Gmail API.
    
    Setup:
    1. Enable Gmail API in Google Cloud Console.
    2. Download `credentials.json`.
    3. Run a local script to generate `token.json` (OAuth2 flow).
    4. Place `token.json` in the root directory (or set GMAIL_TOKEN_PATH).
    """
    try:
        from google.oauth2.credentials import Credentials
        from googleapiclient.discovery import build
        from google.auth.transport.requests import Request
        
        token_path = os.getenv("GMAIL_TOKEN_PATH", "token.json")
        
        # Robust path resolution: if relative path doesn't exist, try looking in the project root
        if not os.path.exists(token_path):
            potential_root_path = os.path.join(os.getcwd(), "token.json")
            if os.path.exists(potential_root_path):
                token_path = potential_root_path
        
        if not os.path.exists(token_path):
            error_msg = f"Gmail token not found at {token_path}."
            
            # Append human observations if available
            obs_path = os.path.join(os.getcwd(), ".exegol", "human_observations.json")
            if os.path.exists(obs_path):
                try:
                    with open(obs_path, 'r', encoding='utf-8') as f:
                        obs = json.load(f)
                    if "gmail" in obs:
                        error_msg += f" Human Observation: {obs['gmail']}"
                    elif "compliance" in obs:
                        error_msg += f" Note: {obs['compliance']}"
                except:
                    pass
            
            return f"Error: {error_msg} Please run `python generate_token.py` to create it."
            
        creds = Credentials.from_authorized_user_file(token_path)
        
        # Automatically refresh the token if it is expired
        if not creds.valid:
            if creds.expired and creds.refresh_token:
                creds.refresh(Request())
                # Save the refreshed credentials back to the file
                with open(token_path, 'w') as token:
                    token.write(creds.to_json())
            else:
                return "Error: Gmail token is invalid or revoked. Please run `python generate_token.py` again."
        
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
        return "Error: google-api-python-client or google-auth not installed. Cannot send Gmail."
    except Exception as e:
        return f"Gmail Send Failure: {str(e)}"
