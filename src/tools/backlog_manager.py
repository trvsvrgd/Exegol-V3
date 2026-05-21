import os
import json
import datetime
import sqlite3
import hashlib
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

    def dedupe_auto_failures(self) -> Dict[str, Any]:
        """Archive repeated active backlog rows that describe the same work.

        The fleet can generate many time-stamped failure IDs for one underlying
        issue. Keep the oldest active task as the canonical row, merge duplicate
        IDs into it, and archive the repeated rows so the board stays actionable.
        """
        active = self.load_backlog()
        groups: Dict[str, List[Dict[str, Any]]] = {}
        for task in active:
            key = self._dedupe_key(task)
            if key:
                groups.setdefault(key, []).append(task)

        duplicate_groups = {
            key: tasks for key, tasks in groups.items()
            if len(tasks) > 1
        }
        if not duplicate_groups:
            return {
                "removed_duplicates": 0,
                "duplicate_groups": 0,
                "canonical_task_ids": [],
                "archived_task_ids": [],
            }

        now_str = datetime.datetime.now().isoformat()
        canonical_task_ids: List[str] = []
        archived_task_ids: List[str] = []

        with self._get_conn() as conn:
            conn.row_factory = sqlite3.Row
            for tasks in duplicate_groups.values():
                ordered = sorted(tasks, key=lambda task: (
                    task.get("created_at") or "",
                    task.get("rank") if task.get("rank") is not None else 999999,
                    task.get("id") or "",
                ))
                canonical = ordered[0]
                duplicates = ordered[1:]
                canonical_id = canonical.get("id")
                if not canonical_id:
                    continue

                merged_ids = list(dict.fromkeys(
                    list(canonical.get("merged_duplicate_ids", []))
                    + [task.get("id") for task in duplicates if task.get("id")]
                ))
                canonical["merged_duplicate_ids"] = merged_ids
                canonical["duplicate_count"] = len(merged_ids)
                canonical["updated_at"] = now_str
                canonical_task_ids.append(canonical_id)

                conn.execute(
                    """
                    UPDATE tasks
                    SET status = ?, priority = ?, type = ?, source_agent = ?,
                        rationale = ?, created_at = ?, rank = ?, data = ?
                    WHERE id = ?
                    """,
                    (
                        canonical.get("status"),
                        canonical.get("priority"),
                        canonical.get("type"),
                        canonical.get("source_agent"),
                        canonical.get("rationale"),
                        canonical.get("created_at"),
                        canonical.get("rank"),
                        json.dumps(canonical),
                        canonical_id,
                    ),
                )

                for duplicate in duplicates:
                    duplicate_id = duplicate.get("id")
                    if not duplicate_id:
                        continue
                    duplicate["archived_at"] = now_str
                    duplicate["archive_reason"] = f"Duplicate of {canonical_id}"
                    duplicate["canonical_task_id"] = canonical_id
                    archived_task_ids.append(duplicate_id)
                    conn.execute(
                        """
                        UPDATE tasks
                        SET archived_at = ?, status = ?, data = ?
                        WHERE id = ?
                        """,
                        (
                            now_str,
                            duplicate.get("status"),
                            json.dumps(duplicate),
                            duplicate_id,
                        ),
                    )
            conn.commit()

        self._sync_to_json()
        return {
            "removed_duplicates": len(archived_task_ids),
            "duplicate_groups": len(duplicate_groups),
            "canonical_task_ids": canonical_task_ids,
            "archived_task_ids": archived_task_ids,
        }

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

    def _dedupe_key(self, task: Dict[str, Any]) -> Optional[str]:
        summary = " ".join(str(task.get("summary") or "").lower().split())
        if not summary:
            return None

        task_id = str(task.get("id") or "")
        source = str(task.get("source") or task.get("source_agent") or "").lower()
        duplicate_prone = (
            task_id.startswith("auto_fail_")
            or task_id.startswith("failure_")
            or source in {"watcher_wedge", "supervisor", "agentic_coding", "ui"}
            or summary.startswith(("fix:", "critical:", "resolve ", "notice:"))
        )
        if not duplicate_prone:
            return None

        digest = hashlib.sha1(summary.encode("utf-8")).hexdigest()
        return digest

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
