import datetime
import json
import os
import sys
from types import SimpleNamespace

os.environ["EXEGOL_DISABLE_SCHEDULER"] = "true"
os.environ["EXEGOL_DISABLE_SLACK"] = "true"
os.environ["SLACK_BOT_TOKEN"] = ""
os.environ["SLACK_APP_TOKEN"] = ""
os.environ["SLACK_WEBHOOK_URL"] = ""

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from tools import supervisor_health


def test_scan_heartbeats_reports_stale_active_session(tmp_path):
    repo_path = tmp_path / "repo"
    heartbeat_dir = repo_path / ".exegol" / "heartbeats"
    heartbeat_dir.mkdir(parents=True)
    old_pulse = (datetime.datetime.now() - datetime.timedelta(seconds=500)).isoformat()
    (heartbeat_dir / "abc123.json").write_text(
        json.dumps(
            {
                "session_id": "abc123",
                "agent_id": "developer_dex",
                "status": "active",
                "last_pulse": old_pulse,
            }
        ),
        encoding="utf-8",
    )

    health = supervisor_health.scan_heartbeats(str(repo_path), ttl_seconds=60)

    assert health["status"] == "degraded"
    assert health["active"] == 0
    assert health["stale"] == 1
    assert health["sessions"][0]["status"] == "stale"
    assert health["sessions"][0]["blocking"] is True


def test_scan_heartbeats_counts_only_current_active_sessions(tmp_path):
    repo_path = tmp_path / "repo"
    heartbeat_dir = repo_path / ".exegol" / "heartbeats"
    heartbeat_dir.mkdir(parents=True)
    current_pulse = datetime.datetime.now().isoformat()
    old_pulse = (datetime.datetime.now() - datetime.timedelta(seconds=500)).isoformat()
    records = {
        "active123.json": {
            "session_id": "active123",
            "agent_id": "developer_dex",
            "status": "active",
            "last_pulse": current_pulse,
        },
        "stale123.json": {
            "session_id": "stale123",
            "agent_id": "watcher_wedge",
            "status": "stale",
            "last_pulse": old_pulse,
        },
        "cleared123.json": {
            "session_id": "cleared123",
            "agent_id": "quality_quigon",
            "status": "cleared",
            "last_pulse": old_pulse,
        },
    }
    for filename, payload in records.items():
        (heartbeat_dir / filename).write_text(json.dumps(payload), encoding="utf-8")

    health = supervisor_health.scan_heartbeats(str(repo_path), ttl_seconds=60)

    assert health["status"] == "ok"
    assert health["active"] == 1
    assert health["stale"] == 0
    assert health["historical_stale"] == 1
    assert health["total"] == 3
    stale_session = next(session for session in health["sessions"] if session["session_id"] == "stale123")
    assert stale_session["status"] == "stale"
    assert stale_session["blocking"] is False


def test_check_docker_reports_missing_cli(monkeypatch):
    def missing_docker(*_args, **_kwargs):
        raise FileNotFoundError()

    monkeypatch.setattr(supervisor_health.subprocess, "run", missing_docker)

    health = supervisor_health.check_docker()

    assert health["status"] == "degraded"
    assert "Docker CLI" in health["detail"]
    assert health["policy"] == "blocked_manual"


def test_endpoint_checks_report_dead_backend_and_frontend(monkeypatch):
    def dead_endpoint(*_args, **_kwargs):
        raise ConnectionRefusedError("refused")

    monkeypatch.setattr(supervisor_health.urllib.request, "urlopen", dead_endpoint)

    backend = supervisor_health.check_http_endpoint("Backend", "http://127.0.0.1:8000/health")
    frontend = supervisor_health.check_http_endpoint("Frontend", "http://127.0.0.1:3000")

    assert backend["status"] == "degraded"
    assert frontend["status"] == "degraded"
    assert backend["policy"] == "report_only"
    assert "unreachable" in backend["detail"]


def test_build_supervisor_health_reports_blocked_repo_and_services(tmp_path, monkeypatch):
    repo_path = tmp_path / "repo"
    exegol_dir = repo_path / ".exegol"
    exegol_dir.mkdir(parents=True)
    (exegol_dir / "fleet_state.json").write_text(
        json.dumps({"status": "blocked", "errors": ["RuntimeError"], "active_agent": "developer_dex"}),
        encoding="utf-8",
    )

    orchestrator = SimpleNamespace(
        priority_config={
            "repositories": [
                {"repo_path": str(repo_path), "agent_status": "blocked"}
            ]
        },
        load_config=lambda: None,
    )
    monkeypatch.setattr(supervisor_health, "check_docker", lambda: {"status": "ok", "detail": "ok"})

    health = supervisor_health.build_supervisor_health(
        orchestrator,
        {"continuous_mode": True, "thread_alive": False, "cycle_running": False},
    )

    assert health["status"] == "degraded"
    assert "autonomous_loop" in health["degraded_services"]
    assert str(repo_path) in health["degraded_repositories"]
    assert health["repositories"][0]["fleet_state"]["status"] == "blocked"


def test_supervisor_reconciles_stale_heartbeat_to_blocked_state(tmp_path, monkeypatch):
    repo_path = tmp_path / "repo"
    heartbeat_dir = repo_path / ".exegol" / "heartbeats"
    heartbeat_dir.mkdir(parents=True)
    old_pulse = (datetime.datetime.now() - datetime.timedelta(seconds=500)).isoformat()
    (heartbeat_dir / "stale123.json").write_text(
        json.dumps(
            {
                "session_id": "stale123",
                "agent_id": "quality_quigon",
                "status": "active",
                "last_pulse": old_pulse,
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(supervisor_health, "check_docker", lambda: {"status": "ok", "detail": "ok"})
    monkeypatch.setattr("tools.fleet_logger.log_interaction", lambda **_kwargs: "log.json")
    orchestrator = SimpleNamespace(
        priority_config={
            "repositories": [
                {"repo_path": str(repo_path), "agent_status": "active"}
            ]
        },
        load_config=lambda: None,
    )

    health = supervisor_health.build_supervisor_health(
        orchestrator,
        {"continuous_mode": False, "thread_alive": False, "cycle_running": False},
    )

    state = json.loads((repo_path / ".exegol" / "fleet_state.json").read_text(encoding="utf-8"))
    events = [
        json.loads(line)
        for line in (repo_path / ".exegol" / "supervisor_events.jsonl").read_text(encoding="utf-8").splitlines()
    ]
    assert health["status"] == "degraded"
    assert state["status"] == "blocked"
    assert state["active_agent"] == "quality_quigon"
    assert state["blocker_type"] == "stale_heartbeat"
    assert state["retry_available"] is True
    assert any(event["event_type"] == "stale_session_blocked" for event in events)

    heartbeat = json.loads((heartbeat_dir / "stale123.json").read_text(encoding="utf-8"))
    assert heartbeat["status"] == "stale"
    assert heartbeat["acknowledge_reason"] == "Supervisor converted stale heartbeat to blocked fleet state."

    follow_up = supervisor_health.scan_heartbeats(str(repo_path))
    assert follow_up["status"] == "ok"
    assert follow_up["stale"] == 0
    assert follow_up["historical_stale"] == 1


def test_dead_scheduler_is_auto_restarted_and_event_persisted(tmp_path, monkeypatch):
    monkeypatch.delenv("EXEGOL_DISABLE_SCHEDULER", raising=False)
    repo_path = tmp_path / "repo"
    repo_path.mkdir()
    monkeypatch.setattr(supervisor_health, "check_docker", lambda: {"status": "ok", "detail": "ok"})

    class AliveThread:
        def is_alive(self):
            return True

    class DeadSchedulerOrchestrator:
        scheduler_thread = None

        def __init__(self):
            self.priority_config = {"repositories": [{"repo_path": str(repo_path), "agent_status": "idle"}]}
            self.restarts = 0

        def load_config(self):
            pass

        def restart_scheduler(self):
            self.restarts += 1
            self.scheduler_thread = AliveThread()
            return True

    orchestrator = DeadSchedulerOrchestrator()

    health = supervisor_health.build_supervisor_health(
        orchestrator,
        {"continuous_mode": False, "thread_alive": False, "cycle_running": False},
    )

    events = [
        json.loads(line)
        for line in (repo_path / ".exegol" / "supervisor_events.jsonl").read_text(encoding="utf-8").splitlines()
    ]
    assert health["services"]["scheduler"]["status"] == "ok"
    assert health["services"]["scheduler"]["action"] == "restarted"
    assert orchestrator.restarts == 1
    assert any(event["event_type"] == "scheduler_restarted" for event in events)


def test_scheduler_restart_failure_stays_degraded_and_is_reported(tmp_path, monkeypatch):
    monkeypatch.delenv("EXEGOL_DISABLE_SCHEDULER", raising=False)
    repo_path = tmp_path / "repo"
    repo_path.mkdir()
    monkeypatch.setattr(supervisor_health, "check_docker", lambda: {"status": "ok", "detail": "ok"})

    orchestrator = SimpleNamespace(
        priority_config={"repositories": [{"repo_path": str(repo_path), "agent_status": "idle"}]},
        scheduler_thread=None,
        load_config=lambda: None,
        restart_scheduler=lambda: False,
    )

    health = supervisor_health.build_supervisor_health(
        orchestrator,
        {"continuous_mode": False, "thread_alive": False, "cycle_running": False},
    )

    events = [
        json.loads(line)
        for line in (repo_path / ".exegol" / "supervisor_events.jsonl").read_text(encoding="utf-8").splitlines()
    ]
    assert health["services"]["scheduler"]["status"] == "degraded"
    assert health["services"]["scheduler"]["action"] == "restart_failed"
    assert "scheduler" in health["degraded_services"]
    assert any(event["event_type"] == "scheduler_restart_failed" for event in events)
