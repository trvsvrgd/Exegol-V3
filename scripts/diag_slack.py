"""Quick diagnostic - checks auth and channel membership."""
import os
from dotenv import load_dotenv
from slack_sdk import WebClient

load_dotenv()
token = os.getenv("SLACK_BOT_TOKEN")
client = WebClient(token=token)

try:
    result = client.auth_test()
    print("Bot User:", result["user"])
    print("Team:    ", result["team"])
    print("Bot ID:  ", result["user_id"])
    print()
    # List channels the bot is in
    channels = client.conversations_list(types="public_channel")
    for c in channels["channels"]:
        status = "[JOINED]" if c.get("is_member") else "[NOT IN]"
        print(f"  {status} #{c['name']} (id: {c['id']})")
except Exception as e:
    print(f"ERROR: {e}")
