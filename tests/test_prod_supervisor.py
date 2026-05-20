import datetime
import json

from tools.prod_supervisor import ProdSupervisor


def test_supervisor_flags_stale_sessions_and_persists_event(tmp_path):
    hb_dir = tmp_path / ".exegol" / "heartbeats"
    hb_dir.mkdir(parents=True)
    old_pulse = datetime.datetime(2026, 5, 19, 10, 0, 0)
    now = datetime.datetime(2026, 5, 19, 10, 5, 0)
    heartbeat = {
        "session_id": "deadbeef",
        "agent_id": "developer_dex",
        "status": "active",
        "last_pulse": old_pulse.isoformat(),
    }
    (hb_dir / "deadbeef.json").write_text(json.dumps(heartbeat), encoding="utf-8")

    result = ProdSupervisor(str(tmp_path), now_fn=lambda: now, heartbeat_ttl_seconds=60).run_once()

    assert result["status"] == "degraded"
    assert result["findings"][0]["component"] == "session"
    updated = json.loads((hb_dir / "deadbeef.json").read_text(encoding="utf-8"))
    assert updated["status"] == "stale"

    events = json.loads((tmp_path / ".exegol" / "supervisor_events.json").read_text(encoding="utf-8"))
    assert any(event["event_type"] == "stale_detected" for event in events)

    queue = json.loads((tmp_path / ".exegol" / "user_action_required.json").read_text(encoding="utf-8"))
    assert queue[0]["blocker_type"] == "stale_heartbeat"


def test_supervisor_restarts_dead_scheduler_without_blocker(tmp_path):
    calls = []
    supervisor = ProdSupervisor(
        str(tmp_path),
        scheduler_probe=lambda: False,
        restart_scheduler=lambda: calls.append("scheduler") or True,
    )

    result = supervisor.run_once()

    assert calls == ["scheduler"]
    assert result["remediations"][0]["outcome"] == "recovered"
    assert not (tmp_path / ".exegol" / "user_action_required.json").exists()


def test_supervisor_reports_docker_unavailable_without_restart(tmp_path):
    supervisor = ProdSupervisor(str(tmp_path), docker_probe=lambda: False)

    result = supervisor.run_once()

    assert result["findings"][0]["component"] == "docker"
    assert result["remediations"][0]["action"] == "report"
    assert result["remediations"][0]["outcome"] == "blocked"
    queue = json.loads((tmp_path / ".exegol" / "user_action_required.json").read_text(encoding="utf-8"))
    assert queue[0]["blocker_type"] == "docker_unavailable"


def test_supervisor_recovery_flow_updates_state_and_events(tmp_path):
    restart_calls = []
    supervisor = ProdSupervisor(
        str(tmp_path),
        backend_probe=lambda: False,
        frontend_probe=lambda: False,
        restart_backend=lambda: restart_calls.append("backend") or True,
        restart_frontend=lambda: restart_calls.append("frontend") or False,
    )

    result = supervisor.run_once()

    assert restart_calls == ["backend", "frontend"]
    outcomes = {item["component"]: item["outcome"] for item in result["remediations"]}
    assert outcomes == {"backend": "recovered", "frontend": "blocked"}

    state = json.loads((tmp_path / ".exegol" / "supervisor_state.json").read_text(encoding="utf-8"))
    assert state["status"] == "degraded"
    queue = json.loads((tmp_path / ".exegol" / "user_action_required.json").read_text(encoding="utf-8"))
    assert queue[0]["blocker_type"] == "agent_crash"
