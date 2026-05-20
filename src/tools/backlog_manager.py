import os
import json
import datetime
import sqlite3
from contextlib import contextmanager
from typing import List, Dict, Any, Optional

from tools.operations import normalize_blocker_type, stable_blocker_id
from tools.state_manager import StateManager

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
        self.sm = StateManager(repo_path)
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
                    rank INTEGER,
                    data TEXT
                )
            """)
            cursor = conn.cursor()
            cursor.execute("PRAGMA table_info(tasks)")
            columns = {row[1] for row in cursor.fetchall()}
            if "rank" not in columns:
                conn.execute("ALTER TABLE tasks ADD COLUMN rank INTEGER")
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
            (id, summary, priority, type, status, source_agent, rationale, created_at, archived_at, rank, data)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
            task.get("rank"),
            json.dumps(task)
        ))

    def dedupe_auto_failures(self) -> Dict[str, Any]:
        """Collapse timestamped auto_fail/crash failures into stable blocker records."""
        active = self.load_backlog()
        archived = self.load_archive()
        combined = active + archived
        groups: Dict[str, List[Dict[str, Any]]] = {}

        for task in combined:
            task_id = str(task.get("id", ""))
            summary = str(task.get("summary", ""))
            if not (task_id.startswith("auto_fail_") or task_id.startswith("crash_") or "hard crash" in summary.lower()):
                continue
            agent = task.get("target_agent") or task.get("source_agent") or task.get("agent_id") or "unknown_agent"
            error = task.get("rationale") or task.get("description") or summary
            stable_subject = f"{agent}:{summary.split(':')[-1].strip() or error[:120]}"
            groups.setdefault(stable_subject, []).append(task)

        if not groups:
            return {"status": "success", "deduped_groups": 0, "removed_duplicates": 0}

        now = datetime.datetime.now().isoformat()
        removed_ids = set()
        replacement_tasks: List[Dict[str, Any]] = []
        for subject, tasks in groups.items():
            if len(tasks) < 2:
                continue
            tasks.sort(key=lambda item: item.get("created_at") or item.get("timestamp") or "")
            canonical = dict(tasks[-1])
            blocker_type = normalize_blocker_type(canonical.get("blocker_type"), "agent_crash")
            canonical["id"] = stable_blocker_id(blocker_type, subject)
            canonical["blocker_type"] = blocker_type
            canonical["status"] = canonical.get("status", "todo")
            canonical["priority"] = canonical.get("priority", "critical")
            canonical["summary"] = canonical.get("summary") or "Agent crash blocker"
            canonical["updated_at"] = now
            canonical["occurrences"] = [
                {
                    "id": item.get("id"),
                    "created_at": item.get("created_at") or item.get("timestamp"),
                    "summary": item.get("summary"),
                    "rationale": item.get("rationale") or item.get("description"),
                }
                for item in tasks
            ]
            canonical["related_failures"] = [item.get("id") for item in tasks if item.get("id")]
            replacement_tasks.append(canonical)
            removed_ids.update(item.get("id") for item in tasks if item.get("id"))

        if not replacement_tasks:
            return {"status": "success", "deduped_groups": 0, "removed_duplicates": 0}

        with self._get_conn() as conn:
            for task_id in removed_ids:
                conn.execute("DELETE FROM tasks WHERE id = ?", (task_id,))
            for task in replacement_tasks:
                self._insert_task(conn, task, archived=False)
            conn.commit()

        self._sync_to_json()
        return {
            "status": "success",
            "deduped_groups": len(replacement_tasks),
            "removed_duplicates": len(removed_ids),
            "blocker_ids": [task["id"] for task in replacement_tasks],
        }

    def load_backlog(self) -> List[Dict[str, Any]]:
        """Loads the active backlog (not archived)."""
        with self._get_conn() as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute("SELECT data FROM tasks WHERE archived_at IS NULL ORDER BY COALESCE(rank, 999999), created_at, id")
            return [json.loads(row["data"]) for row in cursor.fetchall()]

    def load_archive(self) -> List[Dict[str, Any]]:
        """Loads the archived tasks."""
        with self._get_conn() as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute("SELECT data FROM tasks WHERE archived_at IS NOT NULL")
            return [json.loads(row["data"]) for row in cursor.fetchall()]

    def save_backlog_order(self, ordered_task_ids: List[str]) -> bool:
        """Persist UI ordering while keeping all active tasks and SQLite as source of truth."""
        active = self.load_backlog()
        if not ordered_task_ids:
            return False

        task_map = {task.get("id"): task for task in active if task.get("id")}
        ordered = []
        seen = set()
        for task_id in ordered_task_ids:
            task = task_map.get(task_id)
            if task:
                ordered.append(task)
                seen.add(task_id)

        for task in active:
            task_id = task.get("id")
            if task_id not in seen:
                ordered.append(task)

        with self._get_conn() as conn:
            for index, task in enumerate(ordered):
                task["rank"] = index
                conn.execute(
                    "UPDATE tasks SET rank = ?, data = ? WHERE id = ?",
                    (index, json.dumps(task), task.get("id")),
                )
            conn.commit()

        self._sync_to_json()
        return True

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

    def get_task(self, task_id: str) -> Optional[Dict[str, Any]]:
        """Returns a task by ID from the active or archived backlog."""
        with self._get_conn() as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute("SELECT data FROM tasks WHERE id = ?", (task_id,))
            row = cursor.fetchone()
            if not row:
                return None
            return json.loads(row["data"])

    def update_task(self, task_id: str, updates: Dict[str, Any]) -> bool:
        """Updates arbitrary task fields while keeping indexed columns in sync."""
        with self._get_conn() as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute("SELECT data FROM tasks WHERE id = ?", (task_id,))
            row = cursor.fetchone()
            if not row:
                return False

            task = json.loads(row["data"])
            task.update(updates)

            conn.execute(
                """
                UPDATE tasks
                SET summary = ?, priority = ?, type = ?, status = ?,
                    source_agent = ?, rationale = ?, created_at = ?,
                    archived_at = ?, rank = ?, data = ?
                WHERE id = ?
                """,
                (
                    task.get("summary"),
                    task.get("priority"),
                    task.get("type"),
                    task.get("status"),
                    task.get("source_agent"),
                    task.get("rationale"),
                    task.get("created_at"),
                    task.get("archived_at"),
                    task.get("rank"),
                    json.dumps(task),
                    task_id,
                ),
            )
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
            
            conn.execute(
                "UPDATE tasks SET status = ?, rank = ?, data = ? WHERE id = ?",
                (new_status, task.get("rank"), json.dumps(task), task_id),
            )
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
            self.sm.write_json(".exegol/backlog.json", active)
        except Exception as e:
            print(f"[BacklogManager] Failed to sync backlog.json: {e}")
            
        archived = self.load_archive()
        try:
            self.sm.write_json(".exegol/backlog_archive.json", archived)
        except Exception as e:
            print(f"[BacklogManager] Failed to sync backlog_archive.json: {e}")
