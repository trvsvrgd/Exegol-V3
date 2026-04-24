import os
import sys
import json
import requests
from datetime import datetime

# Add src to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'src')))

from tools.slack_tool import slack_manager
from tools.egress_filter import EgressFilter

# Ensure console can handle emojis
if sys.stdout.encoding != 'utf-8':
    try:
        import codecs
        sys.stdout = codecs.getwriter('utf-8')(sys.stdout.buffer, 'strict')
        sys.stderr = codecs.getwriter('utf-8')(sys.stderr.buffer, 'strict')
    except Exception:
        pass

def run_audit():
    """Fetches health metrics from the API and reports to Slack."""
    print(f"[{datetime.now().isoformat()}] Starting Fleet Health Audit...")
    
    api_url = "http://localhost:8000/fleet/health"
    api_key = os.getenv("EXEGOL_API_KEY", "dev-local-key")
    
    try:
        # Validate egress
        EgressFilter.validate_request(api_url)
        
        response = requests.get(
            api_url, 
            headers={"X-API-Key": api_key},
            timeout=10
        )
        response.raise_for_status()
        health_data = response.json()
        
        if not health_data:
            slack_manager.post_message("📊 *Fleet Health Audit*: No active repositories found.")
            return

        blocks = [
            {
                "type": "header",
                "text": {
                    "type": "plain_text",
                    "text": "📊 Fleet Health Audit Report"
                }
            },
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": f"*Timestamp*: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n*Managed Repos*: {len(health_data)}"
                }
            },
            {"type": "divider"}
        ]
        
        for repo in health_data:
            status_emoji = "🟢" if repo["status"] == "idle" else "🔵" if repo["status"] == "active" else "🔴"
            
            repo_text = f"{status_emoji} *{repo['name']}*\n"
            repo_text += f"• *Status*: `{repo['status']}` | *Priority*: `{repo['priority']}`\n"
            repo_text += f"• *Backlog*: `{repo['backlog_count']}` tasks | *HITL Queue*: `{repo['hitl_count']}` items\n"
            
            if repo.get("last_activity"):
                last_time = repo["last_activity"].split("T")[1][:5]
                repo_text += f"• *Last Activity*: `{last_time}` by `{repo['last_agent']}` ({repo['last_outcome']})\n"
            
            blocks.append({
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": repo_text
                }
            })

        slack_manager.post_message(text="Fleet Health Audit Report", blocks=blocks)
        print("Audit complete. Report sent to Slack.")
        
    except Exception as e:
        error_msg = f"❌ *Fleet Health Audit Failed*: {str(e)}"
        print(error_msg)
        slack_manager.post_message(error_msg)

if __name__ == "__main__":
    run_audit()
