import os
import json
import datetime
import tempfile
from typing import List, Dict, Any, Optional

class BacklogManager:
    """Centralized manager for the project backlog and its archive.
    
    Handles loading, saving, status updates, and archiving of tasks to ensure
    data integrity and persistence across the fleet.
    """

    def __init__(self, repo_path: str):
        self.repo_path = repo_path
        self.exegol_dir = os.path.join(repo_path, ".exegol")
        self.backlog_file = os.path.join(self.exegol_dir, "backlog.json")
        self.archive_file = os.path.join(self.exegol_dir, "backlog_archive.json")
        os.makedirs(self.exegol_dir, exist_ok=True)

    def load_backlog(self) -> List[Dict[str, Any]]:
        """Loads the active backlog from backlog.json."""
        return self._load_json(self.backlog_file)

    def load_archive(self) -> List[Dict[str, Any]]:
        """Loads the archived tasks from backlog_archive.json."""
        return self._load_json(self.archive_file)

    def save_backlog(self, backlog: List[Dict[str, Any]]):
        """Saves the active backlog to backlog.json."""
        self._save_json(self.backlog_file, backlog)

    def save_archive(self, archive: List[Dict[str, Any]]):
        """Saves the archived tasks to backlog_archive.json."""
        self._save_json(self.archive_file, archive)

    def add_task(self, task: Dict[str, Any]) -> bool:
        """Adds a new task to the backlog if it doesn't already exist.
        
        Uses 'id' or 'source_requirement_id' for deduplication.
        """
        backlog = self.load_backlog()
        
        # Check for duplicates
        task_id = task.get("id")
        source_id = task.get("source_requirement_id")
        
        for t in backlog:
            if (task_id and t.get("id") == task_id) or \
               (source_id and t.get("source_requirement_id") == source_id):
                return False # Duplicate
                
        backlog.append(task)
        self.save_backlog(backlog)
        return True

    def update_task_status(self, task_id: str, new_status: str) -> bool:
        """Updates the status of a specific task in the active backlog."""
        backlog = self.load_backlog()
        updated = False
        for task in backlog:
            if task.get("id") == task_id:
                task["status"] = new_status
                updated = True
                break
        
        if updated:
            self.save_backlog(backlog)
        return updated

    def archive_completed_tasks(self) -> int:
        """Moves all tasks with status 'completed' (or 'done') to the archive.
        
        Returns the number of tasks archived.
        """
        backlog = self.load_backlog()
        active = []
        to_archive = []
        
        for task in backlog:
            if task.get("status") in ["completed", "done"]:
                # Add archival metadata
                task["archived_at"] = datetime.datetime.now().isoformat()
                to_archive.append(task)
            else:
                active.append(task)
        
        if not to_archive:
            return 0
            
        archive = self.load_archive()
        archive.extend(to_archive)
        
        self.save_archive(archive)
        self.save_backlog(active)
        
        return len(to_archive)

    def _load_json(self, path: str) -> List[Dict[str, Any]]:
        if os.path.exists(path):
            try:
                with open(path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    return data if isinstance(data, list) else []
            except (json.JSONDecodeError, IOError):
                return []
        return []

    def _save_json(self, path: str, data: List[Dict[str, Any]]):
        """Saves data to a JSON file atomically."""
        dir_name = os.path.dirname(os.path.abspath(path))
        with tempfile.NamedTemporaryFile("w", dir=dir_name, suffix=".tmp", delete=False, encoding="utf-8") as tmp:
            json.dump(data, tmp, indent=4)
            tmp_path = tmp.name
        
        try:
            os.replace(tmp_path, path)
        except Exception:
            if os.path.exists(tmp_path):
                os.remove(tmp_path)
            raise
