import json

from tools.state_manager import StateManager


def test_read_json_tolerates_corruption_and_records_recovery(tmp_path):
    exegol = tmp_path / ".exegol"
    exegol.mkdir()
    target = exegol / "backlog.json"
    target.write_text("{not valid json", encoding="utf-8")

    sm = StateManager(str(tmp_path))

    assert sm.read_json(".exegol/backlog.json") is None
    events = json.loads((exegol / "corruption_events.json").read_text(encoding="utf-8"))
    assert events[0]["path"] == ".exegol/backlog.json"
    assert (exegol / "corrupt_json").exists()


def test_write_json_redacts_secret_values(tmp_path):
    sm = StateManager(str(tmp_path))

    sm.write_json(".exegol/fleet_state.json", {"token": "abc123456789012345678901234567890", "safe": "ok"})

    data = json.loads((tmp_path / ".exegol" / "fleet_state.json").read_text(encoding="utf-8"))
    assert data["token"] == "[REDACTED]"
    assert data["safe"] == "ok"


def test_write_fleet_state_preserves_schema_version(tmp_path):
    sm = StateManager(str(tmp_path))

    sm.write_fleet_state({"status": "running"})

    data = json.loads((tmp_path / ".exegol" / "fleet_state.json").read_text(encoding="utf-8"))
    assert data["schema_version"] == 1
    assert data["status"] == "running"
