import os
import requests
import threading
from typing import Optional, Dict, Any, Callable
from slack_sdk import WebClient
from slack_bolt import App
from slack_bolt.adapter.socket_mode import SocketModeHandler

class SlackManager:
    """Manages Slack interactions including sending messages and listening for commands."""
    
    _instance = None
    _lock = threading.Lock()

    def __new__(cls):
        with cls._lock:
            if cls._instance is None:
                cls._instance = super(SlackManager, cls).__new__(cls)
                cls._instance._initialized = False
            return cls._instance

    def __init__(self):
        if self._initialized:
            return
            
        self.bot_token = os.getenv("SLACK_BOT_TOKEN")
        self.app_token = os.getenv("SLACK_APP_TOKEN")
        self.webhook_url = os.getenv("SLACK_WEBHOOK_URL")
        
        self.client = WebClient(token=self.bot_token) if self.bot_token else None
        self.app = App(token=self.bot_token) if self.bot_token else None
        self.handler = None
        
        # Approval tracking: {callback_id: threading.Event()}
        self.pending_approvals: Dict[str, threading.Event] = {}
        self.approval_results: Dict[str, str] = {}
        
        self._initialized = True

    def is_bot_active(self) -> bool:
        return self.bot_token is not None and self.app_token is not None

    def post_message(self, text: str, blocks: Optional[list] = None, channel: Optional[str] = None) -> str:
        """Sends a message to Slack using Bot Token (preferred) or Webhook (fallback)."""
        
        # 1. Try Bot Client
        if self.client:
            try:
                # Default to 'general' or first joined channel if not specified
                target_channel = channel or "general"
                response = self.client.chat_postMessage(
                    channel=target_channel,
                    text=text,
                    blocks=blocks
                )
                if response["ok"]:
                    return "Success: Posted via Bot"
            except Exception as e:
                print(f"[SlackManager] Bot post failed: {e}")

        # 2. Fallback to Webhook
        if self.webhook_url:
            payload = {"text": text}
            if blocks:
                payload["blocks"] = blocks
            try:
                resp = requests.post(self.webhook_url, json=payload)
                resp.raise_for_status()
                return "Success: Posted via Webhook"
            except Exception as e:
                return f"Error: {str(e)}"

        return f"[MOCK SLACK] Message: {text}"

    def setup_listener(self, command_handler: Callable[[str, str], None]):
        """Starts Socket Mode listener in a background thread."""
        if not self.is_bot_active():
            print("[SlackManager] Bot tokens missing. Listener skipped.")
            return

        @self.app.message("")  # Listen to all messages
        def handle_message(message, say):
            _process_incoming(message, say)

        @self.app.event("app_mention")
        def handle_mention(event, say):
            _process_incoming(event, say)

        def _process_incoming(payload, say):
            raw_text = payload.get("text", "") or ""
            channel_id = payload.get("channel")
            # Strip bot mention tokens like <@U12345> from the text
            import re
            clean_text = re.sub(r"<@[A-Z0-9]+>", "", raw_text).strip().lower()
            print(f"[SlackManager] Received Slack message: '{clean_text}' on channel: {channel_id}")
            
            if not clean_text:
                return

            # ACK in Slack so the user knows we heard them
            say(f"⚙️ Exegol received: `{clean_text}` — processing...")
            command_handler(clean_text, channel_id)

        @self.app.action("approve_delete")
        def handle_approve(ack, body):
            ack()
            callback_id = body["actions"][0]["value"]
            self.approval_results[callback_id] = "APPROVED"
            if callback_id in self.pending_approvals:
                self.pending_approvals[callback_id].set()

        @self.app.action("reject_delete")
        def handle_reject(ack, body):
            ack()
            callback_id = body["actions"][0]["value"]
            self.approval_results[callback_id] = "REJECTED"
            if callback_id in self.pending_approvals:
                self.pending_approvals[callback_id].set()

        def run_socket():
            print("[SlackManager] Starting Socket Mode Listener...")
            self.handler = SocketModeHandler(self.app, self.app_token)
            self.handler.connect()  # Use connect instead of start to avoid blocking or signal issues
            import time
            while True:
                time.sleep(1)

        threading.Thread(target=run_socket, daemon=True).start()

# Global Singleton
slack_manager = SlackManager()

def post_to_slack(message: str, channel: Optional[str] = None) -> str:
    """Wrapper for legacy compatibility."""
    return slack_manager.post_message(text=message, channel=channel)

def request_approval_for_delete(file_path: str, reason: str) -> str:
    """Specialized Slack message for deletion approvals with interactive buttons."""
    callback_id = f"delete_{os.path.basename(file_path)}_{threading.get_ident()}"
    
    blocks = [
        {
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": f"🚨 *APPROVAL REQUIRED*: Agent requests to DELETE `{file_path}`\n*Reason*: {reason}"
            }
        },
        {
            "type": "actions",
            "elements": [
                {
                    "type": "button",
                    "text": {"type": "plain_text", "text": "Approve ✅"},
                    "style": "primary",
                    "value": callback_id,
                    "action_id": "approve_delete"
                },
                {
                    "type": "button",
                    "text": {"type": "plain_text", "text": "Reject ❌"},
                    "style": "danger",
                    "value": callback_id,
                    "action_id": "reject_delete"
                }
            ]
        }
    ]

    print(f"\n[Slack] Requesting approval for delete: {file_path}")
    slack_manager.post_message(text=f"Requesting approval to delete {file_path}", blocks=blocks)
    
    # Also print to console
    print("\n" + "="*50)
    print("🚨 SYSTEM PAUSED FOR EXTERNAL APPROVAL 🚨")
    print(f"Agent requests to DELETE file: {file_path}")
    print(f"Reason: {reason}")
    print("="*50)

    if not slack_manager.is_bot_active():
        # Fallback to CLI if bot is not active
        response = input("Type 'APPROVE' to allow deletion, or any other key to reject: ").strip().upper()
        return "APPROVED" if response == "APPROVE" else "REJECTED"

    # Block until Slack action or Timeout
    event = threading.Event()
    slack_manager.pending_approvals[callback_id] = event
    
    print("[Slack] Waiting for response in Slack...")
    # Wait up to 5 minutes
    if event.wait(timeout=300):
        result = slack_manager.approval_results.get(callback_id, "REJECTED")
        print(f"[Slack] Received response: {result}")
        return result
    else:
        print("[Slack] Approval timed out. Defaulting to REJECT.")
        return "REJECTED"
