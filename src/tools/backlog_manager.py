import os
import json
import datetime
import sqlite3
from contextlib import contextmanager
from typing import List, Dict, Any, Optional

class BacklogManager:
    """Centralized manager for the project backlog and its archive using SQLite.
    
    Handles loading, saving, status updates, and archiving of tasks to ensure
    data integrity and persistence across the fleet.
    """

    def __init__(self, repo_path: str):
        self.repo_path = repo_path
        self.exegol_dir = os.path.join(repo_path, ".exegol")
        self.db_path = os.path.join(self.exegol_dir, "backlog.db")
        self.backlog_json = os.path.join(self.exegol_dir, "backlog.json")
        self.archive_json = os.path.join(self.exegol_dir, "backlog_archive.json")
        os.makedirs(self.exegol_dir, exist_ok=True)
        
        self._init_db()
        self._migrate_if_needed()

    @contextmanager
    def _get_conn(self):
        """Context manager that ensures the SQLite connection is always closed."""
        conn = sqlite3.connect(self.db_path)
        try:
            yield conn
        finally:
            conn.close()

    def _init_db(self):
        """Initializes the SQLite database and creates the tasks table."""
        with self._get_conn() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS tasks (
                    id TEXT PRIMARY KEY,
                    summary TEXT,
                    priority TEXT,
                    type TEXT,
                    status TEXT,
                    source_agent TEXT,
                    rationale TEXT,
                    created_at TEXT,
                    archived_at TEXT,
                    data TEXT
                )
            """)
            conn.commit()

    def _migrate_if_needed(self):
        """Migrates tasks from legacy JSON files if the database is empty."""
        with self._get_conn() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT COUNT(*) FROM tasks")
            if cursor.fetchone()[0] > 0:
                return # Already migrated or contains data

            print("[BacklogManager] Migration triggered: importing from JSON...")
            
            # Load from active backlog
            active_tasks = self._load_json_legacy(self.backlog_json)
            for task in active_tasks:
                self._insert_task(conn, task, archived=False)
            
            # Load from archive
            archived_tasks = self._load_json_legacy(self.archive_json)
            for task in archived_tasks:
                self._insert_task(conn, task, archived=True)
            
            conn.commit()
            print(f"[BacklogManager] Migrated {len(active_tasks)} active and {len(archived_tasks)} archived tasks.")

    def _load_json_legacy(self, path: str) -> List[Dict[str, Any]]:
        if os.path.exists(path):
            try:
                with open(path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    return data if isinstance(data, list) else []
            except (json.JSONDecodeError, IOError):
                return []
        return []

    def _insert_task(self, conn, task: Dict[str, Any], archived: bool = False):
        """Inserts a task dictionary into the database."""
        task_id = task.get("id")
        if not task_id:
            return
        
        archived_at = task.get("archived_at")
        if archived and not archived_at:
            archived_at = datetime.datetime.now().isoformat()
            
        conn.execute("""
            INSERT OR IGNORE INTO tasks 
            (id, summary, priority, type, status, source_agent, rationale, created_at, archived_at, data)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            task_id,
            task.get("summary"),
            task.get("priority"),
            task.get("type"),
            task.get("status"),
            task.get("source_agent"),
            task.get("rationale"),
            task.get("created_at"),
            archived_at,
            json.dumps(task)
        ))

    def load_backlog(self) -> List[Dict[str, Any]]:
        """Loads the active backlog (not archived)."""
        with self._get_conn() as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute("SELECT data FROM tasks WHERE archived_at IS NULL")
            return [json.loads(row["data"]) for row in cursor.fetchall()]

    def load_archive(self) -> List[Dict[str, Any]]:
        """Loads the archived tasks."""
        with self._get_conn() as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute("SELECT data FROM tasks WHERE archived_at IS NOT NULL")
            return [json.loads(row["data"]) for row in cursor.fetchall()]

    def add_task(self, task: Dict[str, Any]) -> bool:
        """Adds a new task to the backlog if it doesn't already exist."""
        task_id = task.get("id")
        if not task_id:
            return False
            
        with self._get_conn() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT id FROM tasks WHERE id = ?", (task_id,))
            if cursor.fetchone():
                return False # Duplicate
            
            self._insert_task(conn, task)
            conn.commit()
            
        self._sync_to_json()
        return True

    def update_task_status(self, task_id: str, new_status: str) -> bool:
        """Updates the status of a specific task and refreshes its 'data' blob."""
        with self._get_conn() as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute("SELECT data FROM tasks WHERE id = ?", (task_id,))
            row = cursor.fetchone()
            if not row:
                return False
            
            task = json.loads(row["data"])
            task["status"] = new_status
            
            conn.execute("UPDATE tasks SET status = ?, data = ? WHERE id = ?", 
                         (new_status, json.dumps(task), task_id))
            conn.commit()
            
        self._sync_to_json()
        return True

    def archive_completed_tasks(self) -> int:
        """Moves all completed tasks to archive by setting archived_at."""
        now_str = datetime.datetime.now().isoformat()
        with self._get_conn() as conn:
            cursor = conn.cursor()
            
            # Find tasks to archive
            cursor.execute("SELECT id, data FROM tasks WHERE archived_at IS NULL AND status IN ('completed', 'done')")
            rows = cursor.fetchall()
            if not rows:
                return 0
            
            for task_id, data_str in rows:
                task = json.loads(data_str)
                task["archived_at"] = now_str
                conn.execute("UPDATE tasks SET archived_at = ?, data = ? WHERE id = ?",
                             (now_str, json.dumps(task), task_id))
            
            conn.commit()
            
        self._sync_to_json()
        return len(rows)

    def _sync_to_json(self):
        """Synchronizes the database state to the legacy JSON files."""
        active = self.load_backlog()
        try:
            with open(self.backlog_json, "w", encoding="utf-8") as f:
                json.dump(active, f, indent=4)
        except Exception as e:
            print(f"[BacklogManager] Failed to sync backlog.json: {e}")
            
        archived = self.load_archive()
        try:
            with open(self.archive_json, "w", encoding="utf-8") as f:
                json.dump(archived, f, indent=4)
        except Exception as e:
            print(f"[BacklogManager] Failed to sync backlog_archive.json: {e}")
