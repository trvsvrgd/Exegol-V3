import json

from tools.state_migrations import CURRENT_SCHEMA_VERSION, StateMigrationManager


def test_state_migration_creates_versioned_files_and_backup(tmp_path):
    exegol = tmp_path / ".exegol"
    exegol.mkdir()
    (exegol / "fleet_state.json").write_text(json.dumps({"schema_version": 0}), encoding="utf-8")

    result = StateMigrationManager(str(tmp_path)).migrate()

    state = json.loads((exegol / "fleet_state.json").read_text(encoding="utf-8"))
    assert state["schema_version"] == CURRENT_SCHEMA_VERSION
    assert result["backup_dir"]
    assert (exegol / "backlog.json").exists()
    assert (exegol / "user_action_required.json").exists()
