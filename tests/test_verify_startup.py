import datetime
import json

from scripts import verify_startup


def test_startup_preflight_clears_stale_scheduler_state(tmp_path):
    priority_file = tmp_path / "config" / "priority.json"
    priority_file.parent.mkdir()
    priority_file.write_text(
        json.dumps({"repositories": [{"repo_path": str(tmp_path), "agent_status": "idle"}]}),
        encoding="utf-8",
    )
    fleet_state_file = tmp_path / ".exegol" / "fleet_state.json"
    fleet_state_file.parent.mkdir()
    fleet_state_file.write_text(json.dumps({"status": "idle"}), encoding="utf-8")
    scheduler_state_file = tmp_path / ".exegol" / "scheduler_state.json"
    scheduler_state_file.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "status": "healthy",
                "detail": "heartbeat",
                "registered_jobs": 16,
                "enabled": True,
                "heartbeat": (datetime.datetime.now() - datetime.timedelta(days=1)).isoformat(),
                "updated_at": (datetime.datetime.now() - datetime.timedelta(days=1)).isoformat(),
            }
        ),
        encoding="utf-8",
    )

    verify_startup.repair_blocked_state(
        root=tmp_path,
        priority_file=priority_file,
        fleet_state_file=fleet_state_file,
        scheduler_state_file=scheduler_state_file,
    )

    scheduler_state = json.loads(scheduler_state_file.read_text(encoding="utf-8"))
    assert scheduler_state["status"] == "stopped"
    assert scheduler_state["enabled"] is False
    assert scheduler_state["heartbeat"] is None
    assert scheduler_state["detail"] == "Cleared stale scheduler heartbeat by startup preflight."


def test_startup_preflight_leaves_disabled_scheduler_state_alone(tmp_path):
    priority_file = tmp_path / "config" / "priority.json"
    priority_file.parent.mkdir()
    priority_file.write_text(
        json.dumps({"repositories": [{"repo_path": str(tmp_path), "agent_status": "idle"}]}),
        encoding="utf-8",
    )
    fleet_state_file = tmp_path / ".exegol" / "fleet_state.json"
    fleet_state_file.parent.mkdir()
    fleet_state_file.write_text(json.dumps({"status": "idle"}), encoding="utf-8")
    scheduler_state_file = tmp_path / ".exegol" / "scheduler_state.json"
    original_state = {
        "schema_version": 1,
        "status": "disabled",
        "detail": "disabled in config",
        "enabled": False,
        "heartbeat": None,
    }
    scheduler_state_file.write_text(json.dumps(original_state), encoding="utf-8")

    verify_startup.repair_blocked_state(
        root=tmp_path,
        priority_file=priority_file,
        fleet_state_file=fleet_state_file,
        scheduler_state_file=scheduler_state_file,
    )

    assert json.loads(scheduler_state_file.read_text(encoding="utf-8")) == original_state


def test_startup_preflight_clears_resolved_crash_summary(tmp_path):
    priority_file = tmp_path / "config" / "priority.json"
    priority_file.parent.mkdir()
    priority_file.write_text(
        json.dumps({"repositories": [{"repo_path": str(tmp_path), "agent_status": "idle"}]}),
        encoding="utf-8",
    )
    fleet_state_file = tmp_path / ".exegol" / "fleet_state.json"
    fleet_state_file.parent.mkdir()
    fleet_state_file.write_text(
        json.dumps(
            {
                "active_repo": str(tmp_path),
                "active_agent": "watcher_wedge",
                "status": "done",
                "errors": [],
                "handoff_chain": ["watcher_wedge"],
                "next_agent_id": "product_poe",
                "output_summary": "cannot access local variable 'time' where it is not associated with a value",
            }
        ),
        encoding="utf-8",
    )
    scheduler_state_file = tmp_path / ".exegol" / "scheduler_state.json"
    scheduler_state_file.write_text(json.dumps({"status": "disabled", "enabled": False}), encoding="utf-8")

    verify_startup.repair_blocked_state(
        root=tmp_path,
        priority_file=priority_file,
        fleet_state_file=fleet_state_file,
        scheduler_state_file=scheduler_state_file,
    )

    state = json.loads(fleet_state_file.read_text(encoding="utf-8"))
    assert state["status"] == "idle"
    assert state["active_agent"] is None
    assert state["handoff_chain"] == []
    assert state["next_agent_id"] == ""
    assert state["output_summary"] == "Stale crash summary cleared by startup preflight."
    assert "last_cleared_output_summary" in state
