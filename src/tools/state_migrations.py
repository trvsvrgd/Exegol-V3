import os
import shutil
from datetime import datetime
from typing import Any, Dict

from tools.state_manager import StateManager


CURRENT_SCHEMA_VERSION = 1
SCHEMA_FILES = {
    ".exegol/fleet_state.json": {"schema_version": CURRENT_SCHEMA_VERSION},
    ".exegol/backlog.json": [],
    ".exegol/user_action_required.json": [],
}


class StateMigrationManager:
    def __init__(self, repo_path: str):
        self.repo_path = os.path.abspath(repo_path)
        self.sm = StateManager(self.repo_path)

    def migrate(self) -> Dict[str, Any]:
        backup_dir = self._backup_state()
        changed = []
        for relative_path, default in SCHEMA_FILES.items():
            existing = self.sm.read_json(relative_path)
            if existing is None:
                self.sm.write_json(relative_path, default)
                changed.append({"path": relative_path, "action": "created"})
                continue
            if isinstance(existing, dict):
                old_version = int(existing.get("schema_version", 0) or 0)
                if old_version < CURRENT_SCHEMA_VERSION:
                    existing["schema_version"] = CURRENT_SCHEMA_VERSION
                    existing["migrated_at"] = datetime.now().isoformat()
                    self.sm.write_json(relative_path, existing)
                    changed.append({"path": relative_path, "action": "upgraded", "from": old_version})

        manifest = {
            "schema_version": CURRENT_SCHEMA_VERSION,
            "timestamp": datetime.now().isoformat(),
            "backup_dir": backup_dir,
            "changed": changed,
        }
        self.sm.write_json(".exegol/schema_migration.json", manifest)
        return manifest

    def _backup_state(self) -> str:
        exegol_dir = os.path.join(self.repo_path, ".exegol")
        backup_dir = os.path.join(exegol_dir, "schema_backups", datetime.now().strftime("%Y%m%d%H%M%S"))
        os.makedirs(backup_dir, exist_ok=True)
        for relative_path in SCHEMA_FILES:
            source = os.path.join(self.repo_path, relative_path)
            if os.path.exists(source):
                shutil.copy2(source, os.path.join(backup_dir, os.path.basename(source)))
        return backup_dir
