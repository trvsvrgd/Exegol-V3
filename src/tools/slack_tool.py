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
        
        self.mapping_file = os.path.join(os.getenv("EXEGOL_REPO_PATH", "."), ".exegol", "slack_mapping.json")
        self.hitl_mapping = self._load_mapping()
        
        self._initialized = True

    def _load_mapping(self) -> Dict[str, Any]:
        if os.path.exists(self.mapping_file):
            try:
                with open(self.mapping_file, "r", encoding="utf-8") as f:
                    return json.load(f)
            except:
                return {}
        return {}

    def _save_mapping(self):
        os.makedirs(os.path.dirname(self.mapping_file), exist_ok=True)
        try:
            with open(self.mapping_file, "w", encoding="utf-8") as f:
                json.dump(self.hitl_mapping, f, indent=4)
        except Exception as e:
            print(f"[SlackManager] Failed to save mapping: {e}")

    def is_bot_active(self) -> bool:
        return self.bot_token is not None and self.app_token is not None

    def post_message(self, text: str, blocks: Optional[list] = None, channel: Optional[str] = None) -> str:
        """Sends a message to Slack using Bot Token (preferred) or Webhook (fallback)."""
        
        # 1. Try Bot Client
        if self.client:
            try:
                # Default to 'exegol' or first joined channel if not specified
                target_channel = channel or "exegol"
                response = self.client.chat_postMessage(
                    channel=target_channel,
                    text=text,
                    blocks=blocks
                )
                if response["ok"]:
                    return {"status": "success", "ts": response["ts"], "channel": response["channel"]}
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
                return {"status": "success", "mode": "webhook"}
            except Exception as e:
                print(f"[SlackManager] Webhook post failed: {e}")
                return {"status": "error", "detail": str(e)}

        # 3. Final Fallback: [MOCK SLACK] for development/missing tokens
        print(f"[MOCK SLACK] Channel: {channel or 'exegol'} | Text: {text}")
        
        # Still log to backlog so we know we're in mock mode if it was unexpected
        if not self.bot_token and not self.webhook_url:
            try:
                repo_path = os.environ.get("EXEGOL_REPO_PATH", ".")
                from tools.backlog_manager import BacklogManager
                import datetime
                import time
                
                bm = BacklogManager(repo_path)
                mock_notice = {
                    "id": f"slack_mock_{int(time.time())}",
                    "summary": "NOTICE: Slack running in [MOCK] mode",
                    "priority": "low",
                    "type": "maintenance",
                    "status": "todo",
                    "source_agent": "SlackManager",
                    "rationale": "SLACK_BOT_TOKEN and SLACK_WEBHOOK_URL are missing. System is using [MOCK SLACK] fallback.",
                    "created_at": datetime.datetime.now().isoformat()
                }
                bm.add_task(mock_notice)
            except:
                pass

        return {"status": "success", "mode": "mock", "ts": f"mock_{int(time.time())}"}

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

        @self.app.action("hitl_approve")
        def handle_hitl_approve(ack, body):
            ack()
            item_id = body["actions"][0]["value"]
            repo_path = os.environ.get("EXEGOL_REPO_PATH", ".")
            
            from tools.hitl_manager import HITLManager
            hm = HITLManager(repo_path)
            
            if hm.resolve_task(item_id, status="done", notes="[Slack] Approved by user."):
                # Notify the channel of the update
                channel_id = body["channel"]["id"]
                ts = body["message"]["ts"]
                self.client.chat_update(
                    channel=channel_id,
                    ts=ts,
                    text=f"✅ Task `{item_id}` Approved via Slack.",
                    blocks=[{
                        "type": "section",
                        "text": {"type": "mrkdwn", "text": f"✅ *HITL APPROVED*: Task `{item_id}` has been marked as done."}
                    }]
                )

        @self.app.action("hitl_reject")
        def handle_hitl_reject(ack, body):
            ack()
            item_id = body["actions"][0]["value"]
            repo_path = os.environ.get("EXEGOL_REPO_PATH", ".")
            
            from tools.hitl_manager import HITLManager
            hm = HITLManager(repo_path)
            
            if hm.resolve_task(item_id, status="rejected", notes="[Slack] Rejected by user."):
                # Notify the channel of the update
                channel_id = body["channel"]["id"]
                ts = body["message"]["ts"]
                self.client.chat_update(
                    channel=channel_id,
                    ts=ts,
                    text=f"❌ Task `{item_id}` Rejected via Slack.",
                    blocks=[{
                        "type": "section",
                        "text": {"type": "mrkdwn", "text": f"❌ *HITL REJECTED*: Task `{item_id}` has been rejected."}
                    }]
                )

        def run_socket():
            print("[SlackManager] Starting Socket Mode Listener...")
            self.handler = SocketModeHandler(self.app, self.app_token)
            self.handler.connect()  # Use connect instead of start to avoid blocking or signal issues
            import time
            while True:
                time.sleep(1)

        threading.Thread(target=run_socket, daemon=True).start()

    def update_hitl_status(self, item_id: str, status: str):
        """Updates the Slack message for a HITL task when resolved via another surface."""
        if not self.client or item_id not in self.hitl_mapping:
            return

        mapping = self.hitl_mapping[item_id]
        ts = mapping.get("ts")
        channel = mapping.get("channel")
        task_text = mapping.get("task", item_id)

        if not ts or not channel:
            return

        emoji = "✅" if status == "done" else "❌"
        status_label = "APPROVED" if status == "done" else "REJECTED" if status == "rejected" else status.upper()

        try:
            self.client.chat_update(
                channel=channel,
                ts=ts,
                text=f"{emoji} Task `{item_id}` {status_label} via Fleet Console.",
                blocks=[{
                    "type": "section",
                    "text": {"type": "mrkdwn", "text": f"{emoji} *HITL {status_label}*: {task_text} (ID: `{item_id}`)"}
                }]
            )
            print(f"[SlackManager] Updated message for {item_id} to {status}")
        except Exception as e:
            print(f"[SlackManager] Failed to update message {ts}: {e}")

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
                    "action_id": "hitl_approve"
                },
                {
                    "type": "button",
                    "text": {"type": "plain_text", "text": "Reject ❌"},
                    "style": "danger",
                    "value": callback_id,
                    "action_id": "hitl_reject"
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

def post_hitl_request(item_id: str, task: str, context: str, category: str):
    """Broadcasts a HITL task from the unified queue to Slack and tracks the message ID."""
    blocks = [
        {
            "type": "header",
            "text": {
                "type": "plain_text",
                "text": "🚨 Human Intervention Required"
            }
        },
        {
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": f"*Task:* {task}\n*Category:* `{category}`\n*Context:* {context}"
            }
        },
        {
            "type": "actions",
            "elements": [
                {
                    "type": "button",
                    "text": {"type": "plain_text", "text": "Approve ✅"},
                    "style": "primary",
                    "value": item_id,
                    "action_id": "hitl_approve"
                },
                {
                    "type": "button",
                    "text": {"type": "plain_text", "text": "Reject ❌"},
                    "style": "danger",
                    "value": item_id,
                    "action_id": "hitl_reject"
                },
                {
                    "type": "button",
                    "text": {"type": "plain_text", "text": "View Workbench 🌐"},
                    "url": os.getenv("EXEGOL_FRONTEND_URL", "http://localhost:3000")
                }
            ]
        }
    ]
    
    res = slack_manager.post_message(text=f"HITL Required: {task}", blocks=blocks)
    
    if isinstance(res, dict) and res.get("status") == "success" and "ts" in res:
        slack_manager.hitl_mapping[item_id] = {
            "ts": res["ts"],
            "channel": res["channel"],
            "task": task
        }
        slack_manager._save_mapping()

def post_backlog_update(task_summary: str, priority: str, agent_id: str):
    """Broadcasts a new backlog task to Slack."""
    emoji = "🔥" if priority == "high" else "📋"
    message = f"{emoji} *New Backlog Task*: {task_summary}\n*Priority*: `{priority}`\n*Target Agent*: `{agent_id}`"
    slack_manager.post_message(text=message)
