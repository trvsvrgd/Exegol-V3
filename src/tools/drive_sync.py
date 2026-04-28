import os
from typing import Optional

def drive_sync_file(file_path: str, folder_name: str = "NotebookLM_Source") -> str:
    """Automates file uploads to a specific Google Drive folder.
    
    Setup:
    1. Enable Google Drive API in Google Cloud Console.
    2. Use the same OAuth2 `token.json` used by gmail_tool or a dedicated one.
    3. Place `token.json` in the root directory (or set DRIVE_TOKEN_PATH).

    Fallback: Mocks the upload if credentials are missing.
    """
    try:
        from google.oauth2.credentials import Credentials
        from googleapiclient.discovery import build
        from googleapiclient.http import MediaFileUpload
        
        token_path = os.getenv("DRIVE_TOKEN_PATH", "token.json")
        
        if not os.path.exists(token_path):
            # Fallback for local development without keys
            print(f"[DriveSync] WARNING: Drive token not found at {token_path}. Mocking upload.")
            return f"Mock Success: File '{os.path.basename(file_path)}' would be synced to '{folder_name}'"

        creds = Credentials.from_authorized_user_file(token_path)
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
