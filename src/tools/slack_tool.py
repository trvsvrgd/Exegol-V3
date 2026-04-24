import os
import requests
import threading
from typing import Optional, Dict, Any, Callable
from slack_sdk import WebClient
from slack_bolt import App
from slack_bolt.adapter.socket_mode import SocketModeHandler
from tools.egress_filter import EgressFilter

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
                EgressFilter.validate_request(self.webhook_url)
                resp = requests.post(self.webhook_url, json=payload)
                resp.raise_for_status()
                return "Success: Posted via Webhook"
            except Exception as e:
                print(f"[SlackManager] Webhook post failed: {e}")
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
            
            # Reward Trust (slow gain)
            active_agent = os.getenv("EXEGOL_ACTIVE_AGENT")
            if active_agent:
                from tools.trust_manager import TrustManager
                TrustManager.update_score(active_agent, 1, "User approved HITL request")

            if callback_id in self.pending_approvals:
                self.pending_approvals[callback_id].set()

        @self.app.action("reject_delete")
        def handle_reject(ack, body):
            ack()
            callback_id = body["actions"][0]["value"]
            self.approval_results[callback_id] = "REJECTED"
            
            # Penalize Trust (fast loss)
            active_agent = os.getenv("EXEGOL_ACTIVE_AGENT")
            if active_agent:
                from tools.trust_manager import TrustManager
                TrustManager.update_score(active_agent, -15, "User rejected HITL request")

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

def request_file_approval(file_path: str, action: str, reason: str, risk_score: float = 0.5, risk_label: str = "MEDIUM", risk_reason: str = "Standard review required.") -> str:
    """Specialized Slack message for file modification approvals with interactive buttons and risk assessment."""
    callback_id = f"{action.lower()}_{os.path.basename(file_path)}_{threading.get_ident()}"
    
    # Action styling
    action_verb = "DELETE" if action.upper() == "DELETE" else "OVERWRITE"
    emoji = "🚨" if risk_score >= 0.7 else "⚠️"

    blocks = [
        {
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": f"{emoji} *APPROVAL REQUIRED*: Agent requests to *{action_verb}* `{file_path}`\n*Reason*: {reason}"
            }
        },
        {
            "type": "section",
            "fields": [
                {
                    "type": "mrkdwn",
                    "text": f"*Risk Level*: `{risk_label}` ({risk_score})"
                },
                {
                    "type": "mrkdwn",
                    "text": f"*Assessment*: {risk_reason}"
                }
            ]
        },
        {
            "type": "actions",
            "elements": [
                {
                    "type": "button",
                    "text": {"type": "plain_text", "text": "Approve ✅"},
                    "style": "primary",
                    "value": callback_id,
                    "action_id": "approve_delete"  # We can reuse the same action IDs as they handle the callback_id the same way
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

    print(f"\n[Slack] Requesting approval for {action_verb}: {file_path} (Risk: {risk_label})")
    slack_manager.post_message(text=f"Requesting approval to {action_verb} {file_path}", blocks=blocks)
    
    # Also print to console
    print("\n" + "="*50)
    print("🚨 SYSTEM PAUSED FOR EXTERNAL APPROVAL 🚨")
    print(f"Agent requests to {action_verb} file: {file_path}")
    print(f"Reason: {reason}")
    print(f"Risk: {risk_label} ({risk_score})")
    print("="*50)

    if not slack_manager.is_bot_active():
        # Fallback to CLI if bot is not active
        response = input(f"Type 'APPROVE' to allow {action_verb}, or any other key to reject: ").strip().upper()
        return "APPROVED" if response == "APPROVE" else "REJECTED"

    # Block until Slack action or Timeout
    event = threading.Event()
    slack_manager.pending_approvals[callback_id] = event
    
    # As per policy: Critical risk (1.0) must require HITL until approval (no timeout)
    wait_timeout = None if risk_score >= 1.0 else 300
    
    if wait_timeout is None:
        print("[Slack] CRITICAL RISK: Waiting indefinitely for response in Slack...")
    else:
        print(f"[Slack] Waiting up to {wait_timeout}s for response in Slack...")
        
    if event.wait(timeout=wait_timeout):
        result = slack_manager.approval_results.get(callback_id, "REJECTED")
        print(f"[Slack] Received response: {result}")
        return result
    else:
        print("[Slack] Approval timed out. Defaulting to REJECT.")
        return "REJECTED"
