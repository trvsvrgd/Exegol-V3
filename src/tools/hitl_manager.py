import os
import json
import datetime
import uuid
from typing import List, Dict, Any, Optional
from tools.state_manager import StateManager

class HITLManager:
    """Central manager for Human-In-The-Loop (HITL) actions across all surfaces.
    
    Synchronizes the vibe-coding chat, Exegol UI, and Slack interaction layers.
    """
    
    def __init__(self, repo_path: str):
        self.repo_path = repo_path
        self.sm = StateManager(repo_path)
        self.queue_file = ".exegol/user_action_required.json"

    def get_queue(self) -> List[Dict[str, Any]]:
        """Returns the full HITL queue."""
        return self.sm.read_json(self.queue_file) or []

    def get_pending(self) -> List[Dict[str, Any]]:
        """Returns only pending tasks."""
        return [item for item in self.get_queue() if item.get("status") != "done"]

    def add_task(self, task: str, context: str, category: str = "general", task_id: Optional[str] = None) -> str:
        """Adds a new task to the queue and notifies Slack."""
        # Use StateManager's existing logic which now includes Slack notification
        return self.sm.add_hitl_task(task, category, context, task_id=task_id)

    def resolve_task(self, item_id: str, status: str = "done", notes: Optional[str] = None) -> bool:
        """Resolves a task and ensures consistency across surfaces."""
        queue = self.get_queue()
        updated = False
        
        for item in queue:
            if item.get("id") == item_id:
                item["status"] = status
                if status == "done":
                    item["completed_at"] = datetime.datetime.now().isoformat()
                if notes is not None:
                    item["notes"] = notes
                updated = True
                break
        
        if updated:
            self.sm.write_json(self.queue_file, queue)
            # Sync to Markdown for visibility
            self._sync_to_markdown(queue)
            
            # --- PHASE 2: Sync to Slack ---
            try:
                from tools.slack_tool import slack_manager
                slack_manager.update_hitl_status(item_id, status)
            except Exception as e:
                print(f"[HITLManager] Failed to sync to Slack: {e}")
                
            return True
        return False

    def _sync_to_markdown(self, queue: List[Dict[str, Any]]):
        """Rebuilds the Markdown version of the queue to match the JSON truth."""
        md_path = os.path.join(self.repo_path, ".exegol", "user_action_required.md")
        
        content = "# Exegol V3 - Human Action Required\n"
        content += "## 🚨 Critical Escalations & Manual Tasks\n\n"
        
        for item in queue:
            status_box = "[x]" if item.get("status") == "done" else "[ ]"
            content += f"- {status_box} **{item.get('task')}** (ID: `{item.get('id')}`)\n"
            content += f"  - *Category:* {item.get('category')}\n"
            content += f"  - *Context:* {item.get('context')}\n"
            if item.get("notes"):
                content += f"  - *Notes:* {item.get('notes')}\n"
            content += f"  - *Timestamp:* {item.get('timestamp')}\n\n"
            
        try:
            with open(md_path, 'w', encoding='utf-8') as f:
                f.write(content)
        except Exception as e:
            print(f"[HITLManager] Failed to sync to markdown: {e}")
