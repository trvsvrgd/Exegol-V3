from google_auth_oauthlib.flow import InstalledAppFlow
import os

# Scopes required for sending email
SCOPES = [
    'https://www.googleapis.com/auth/gmail.send',
    'https://www.googleapis.com/auth/drive.file'
]

def main():
    if not os.path.exists('credentials.json'):
        print("Error: 'credentials.json' not found in the current directory.")
        print("Please download it from the Google Cloud Console (APIs & Services > Credentials).")
        return

    # Start the OAuth flow
    flow = InstalledAppFlow.from_client_secrets_file('credentials.json', SCOPES)
    creds = flow.run_local_server(port=0)
    
    # Save the token for Exegol_v3 to use
    with open('token.json', 'w') as token:
        token.write(creds.to_json())
        
    print("\nSUCCESS: 'token.json' has been generated.")
    print("Exegol_v3 is now ready to send emails using your new account.")

if __name__ == '__main__':
    main()
