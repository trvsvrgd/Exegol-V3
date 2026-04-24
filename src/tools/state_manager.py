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
            fd, temp_path = tempfile.mkstemp(dir=os.path.dirname(abs_path), prefix=".state_", suffix=".json")
            try:
                with os.fdopen(fd, 'w', encoding='utf-8') as tmp:
                    json.dump(data, tmp, indent=4)
                
                # Replace the original file with the temporary one atomically
                os.replace(temp_path, abs_path)
            except Exception as e:
                print(f"[StateManager] Error writing {relative_path}: {e}")
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
