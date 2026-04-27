import os
import json
import time
import tempfile
import shutil
from typing import Dict, Any, List, Optional
from threading import Lock

# Process-level lock for the current instance
_global_lock = Lock()

class StateManager:
    """Manages state file interactions with simple atomic writes and relative path handling.
    
    Provides basic protection against partial writes by writing to a temporary file 
    and then renaming it to the target path.
    """

    def __init__(self, repo_path: str):
        self.repo_path = repo_path

    def read_json(self, relative_path: str) -> Optional[Any]:
        """Reads a JSON file safely."""
        abs_path = os.path.join(self.repo_path, relative_path)
        if not os.path.exists(abs_path):
            return None
        
        with _global_lock:
            try:
                with open(abs_path, "r", encoding="utf-8") as f:
                    return json.load(f)
            except (json.JSONDecodeError, IOError) as e:
                print(f"[StateManager] Error reading {relative_path}: {e}")
                return None

    def write_json(self, relative_path: str, data: Any):
        """Writes a JSON file atomically to prevent data corruption."""
        abs_path = os.path.join(self.repo_path, relative_path)
        os.makedirs(os.path.dirname(abs_path), exist_ok=True)
        
        with _global_lock:
            # Atomic write pattern: write to temp file, then rename
            target_dir = os.path.dirname(abs_path)
            with tempfile.NamedTemporaryFile('w', dir=target_dir, prefix=".state_", suffix=".json", encoding='utf-8', delete=False) as tmp:
                temp_path = tmp.name
                try:
                    json.dump(data, tmp, indent=4)
                    tmp.flush()
                    os.fsync(tmp.fileno()) # Ensure data is written to disk
                except Exception as e:
                    print(f"[StateManager] Error writing to temp file: {e}")
                    if os.path.exists(temp_path):
                        os.remove(temp_path)
                    raise e
            
            try:
                # Replace the original file with the temporary one atomically
                os.replace(temp_path, abs_path)
            except Exception as e:
                print(f"[StateManager] Error replacing {relative_path}: {e}")
                if os.path.exists(temp_path):
                    os.remove(temp_path)
                raise e

    def update_backlog_task(self, task_id: str, updates: Dict[str, Any]) -> bool:
        """Specific helper to update a task in backlog.json."""
        backlog = self.read_json(".exegol/backlog.json") or []
        updated = False
        for task in backlog:
            if task.get("id") == task_id:
                task.update(updates)
                updated = True
                break
        
        if updated:
            self.write_json(".exegol/backlog.json", backlog)
        return updated

    def add_hitl_task(self, summary: str, category: str, context: str, task_id: Optional[str] = None) -> str:
        """Standardized method to escalate a task to the human-in-the-loop queue.
        
        Updates both the JSON queue (for Control Tower UI) and the Markdown report.
        """
        import hashlib
        import datetime
        
        timestamp = datetime.datetime.now().isoformat()
        if not task_id:
             task_id = f"hitl_{hashlib.md5(summary.encode()).hexdigest()[:8]}"
        
        # 1. Update JSON
        json_path = ".exegol/user_action_required.json"
        queue = self.read_json(json_path) or []
        
        # Check if already exists (prevent duplicates)
        exists = False
        for item in queue:
            if item.get("id") == task_id or (item.get("task") == summary and item.get("status") != "done"):
                exists = True
                break
        
        if not exists:
            queue.append({
                "id": task_id,
                "task": summary,
                "category": category,
                "context": context,
                "status": "pending",
                "notes": "",
                "timestamp": timestamp
            })
            self.write_json(json_path, queue)
            
        # 2. Update Markdown
        md_path = os.path.join(self.repo_path, ".exegol", "user_action_required.md")
        os.makedirs(os.path.dirname(md_path), exist_ok=True)
        
        entry = f"\n- [ ] **{summary}**\n  - *Category:* {category}\n  - *Context:* {context}\n  - *Timestamp:* {timestamp}\n"
        
        try:
            if os.path.exists(md_path):
                # Check if this task is already in the MD to avoid visual spam
                with open(md_path, 'r', encoding='utf-8') as f:
                    if summary not in f.read():
                        with open(md_path, 'a', encoding='utf-8') as f:
                            f.write(entry)
            else:
                with open(md_path, 'w', encoding='utf-8') as f:
                    f.write("# Exegol V3 - Human Action Required\n")
                    f.write("## 🚨 Critical Escalations & Manual Tasks\n")
                    f.write(entry)
        except Exception as e:
            print(f"[StateManager] Failed to update UAR markdown: {e}")
                
        return task_id
