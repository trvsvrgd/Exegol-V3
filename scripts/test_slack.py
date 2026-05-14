"""
Minimal Slack test - run this to verify Socket Mode is working independently.
python test_slack.py
"""
import os
import re
from dotenv import load_dotenv

load_dotenv()

bot_token = os.getenv("SLACK_BOT_TOKEN")
app_token = os.getenv("SLACK_APP_TOKEN")

print(f"BOT_TOKEN present: {bool(bot_token)} (starts with: {bot_token[:12] if bot_token else 'N/A'})")
print(f"APP_TOKEN present: {bool(app_token)} (starts with: {app_token[:12] if app_token else 'N/A'})")

if not bot_token or not app_token:
    print("\n❌ Tokens missing from .env - check your file.")
    exit(1)

from slack_bolt import App
from slack_bolt.adapter.socket_mode import SocketModeHandler

app = App(token=bot_token)

@app.event("message")
def handle_message_event(event, say):
    text = event.get("text", "") or ""
    clean = re.sub(r"<@[A-Z0-9]+>", "", text).strip()
    print(f"[OK] MESSAGE RECEIVED: '{clean}'")
    say(f"Exegol heard you: `{clean}`")

@app.event("app_mention")
def handle_mention(event, say):
    text = event.get("text", "") or ""
    clean = re.sub(r"<@[A-Z0-9]+>", "", text).strip()
    print(f"[OK] MENTION RECEIVED: '{clean}'")
    say(f"Exegol heard your mention: `{clean}`")

print("\nConnecting to Slack via Socket Mode...")
print(">>> Now type anything in your Slack channel. You should see it appear here.\n")

handler = SocketModeHandler(app, app_token)
handler.start()  # Blocking - runs in main thread (correct for testing)
