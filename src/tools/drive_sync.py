import os
import json
from typing import Optional

def drive_sync_file(file_path: str, folder_name: str = "NotebookLM_Source") -> str:
    """Automates file uploads to a specific Google Drive folder.
    
    Setup:
    1. Enable Google Drive API in Google Cloud Console.
    2. Use the same OAuth2 `token.json` used by gmail_tool or a dedicated one.
    3. Place `token.json` in the root directory (or set DRIVE_TOKEN_PATH).
    """
    try:
        from google.oauth2.credentials import Credentials
        from googleapiclient.discovery import build
        from googleapiclient.http import MediaFileUpload
        from google.auth.transport.requests import Request
        
        token_path = os.getenv("DRIVE_TOKEN_PATH", "token.json")
        
        # Robust path resolution: if relative path doesn't exist, try looking in the project root
        if not os.path.exists(token_path):
            potential_root_path = os.path.join(os.getcwd(), "token.json")
            if os.path.exists(potential_root_path):
                token_path = potential_root_path
        
        if not os.path.exists(token_path):
            error_msg = f"Drive token not found at {token_path}."
            
            # Append human observations if available
            obs_path = os.path.join(os.getcwd(), ".exegol", "human_observations.json")
            if os.path.exists(obs_path):
                try:
                    with open(obs_path, 'r', encoding='utf-8') as f:
                        obs = json.load(f)
                    if "drive" in obs:
                        error_msg += f" Human Observation: {obs['drive']}"
                    elif "compliance" in obs:
                        error_msg += f" Note: {obs['compliance']}"
                except:
                    pass
            
            raise FileNotFoundError(f"{error_msg} Please run `python generate_token.py` to create it.")

        creds = Credentials.from_authorized_user_file(token_path)
        
        # Automatically refresh the token if it is expired
        if not creds.valid:
            if creds.expired and creds.refresh_token:
                creds.refresh(Request())
                # Save the refreshed credentials back to the file
                with open(token_path, 'w') as token:
                    token.write(creds.to_json())
            else:
                raise RuntimeError("Drive token is invalid or revoked. Please run `python generate_token.py` again.")
        
        service = build('drive', 'v3', credentials=creds)
        
        # 1. Find or create the folder
        query = f"name = '{folder_name}' and mimeType = 'application/vnd.google-apps.folder' and trashed = false"
        results = service.files().list(q=query, spaces='drive', fields='files(id, name)').execute()
        items = results.get('files', [])
        
        if not items:
            print(f"[DriveSync] Folder '{folder_name}' not found. Creating it...")
            file_metadata = {
                'name': folder_name,
                'mimeType': 'application/vnd.google-apps.folder'
            }
            folder = service.files().create(body=file_metadata, fields='id').execute()
            folder_id = folder.get('id')
        else:
            folder_id = items[0].get('id')
            
        # 2. Upload the file
        file_name = os.path.basename(file_path)
        file_metadata = {
            'name': file_name,
            'parents': [folder_id]
        }
        
        media = MediaFileUpload(file_path, resumable=True)
        file = service.files().create(body=file_metadata, media_body=media, fields='id').execute()
        
        return f"Success: Synced '{file_name}' to Google Drive (ID: {file.get('id')})"
        
    except ImportError:
        return "Error: google-api-python-client not installed. Cannot perform Drive sync."
    except Exception as e:
        return f"Drive Sync Failure: {str(e)}"
