import json
import os
import sys

os.environ["EXEGOL_DISABLE_SCHEDULER"] = "true"
os.environ["EXEGOL_DISABLE_SLACK"] = "true"
os.environ["SLACK_BOT_TOKEN"] = ""
os.environ["SLACK_APP_TOKEN"] = ""
os.environ["SLACK_WEBHOOK_URL"] = ""

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

import api
import orchestrator as orchestrator_module
from orchestrator import ExegolOrchestrator


def test_blocked_state_survives_backend_restart_visibility(tmp_path, monkeypatch):
    repo_path = tmp_path / "repo"
    exegol_dir = repo_path / ".exegol"
    exegol_dir.mkdir(parents=True)
    (exegol_dir / "fleet_state.json").write_text(
        json.dumps(
            {
                "active_repo": str(repo_path),
                "active_agent": "developer_dex",
                "session_id": "crash123",
                "status": "blocked",
                "handoff_chain": ["product_poe"],
                "next_agent_id": "",
                "monologue": [],
                "errors": ["RuntimeError: crash"],
                "output_summary": "Agent execution failed.",
                "retry_available": True,
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(
        api.orchestrator,
        "priority_config",
        {"repositories": [{"repo_path": str(repo_path), "agent_status": "idle"}]},
    )

    state = api.get_fleet_active_state(str(repo_path))

    assert state["status"] == "blocked"
    assert state["active_agent"] == "developer_dex"
    assert state["retry_available"] is True


def test_retry_after_restart_clears_blocked_state(tmp_path, monkeypatch):
    repo_path = tmp_path / "repo"
    exegol_dir = repo_path / ".exegol"
    exegol_dir.mkdir(parents=True)
    state_file = exegol_dir / "fleet_state.json"
    state_file.write_text(
        json.dumps(
            {
                "active_repo": str(repo_path),
                "active_agent": "developer_dex",
                "session_id": "crash123",
                "status": "blocked",
                "errors": ["RuntimeError: crash"],
                "output_summary": "Agent execution failed.",
                "retry_available": True,
            }
        ),
        encoding="utf-8",
    )
    priority_file = tmp_path / "priority.json"
    history_file = tmp_path / "job_history.json"
    priority_file.write_text(
        json.dumps(
            {
                "repositories": [
                    {
                        "repo_path": str(repo_path),
                        "priority": 1,
                        "agent_status": "idle",
                        "model_routing_preference": "ollama",
                    }
                ],
                "global_settings": {"context_isolation": {}, "compliance_monitoring": {}},
            }
        ),
        encoding="utf-8",
    )

    monkeypatch.setattr(orchestrator_module, "PRIORITY_FILE_PATH", str(priority_file))
    monkeypatch.setattr(orchestrator_module, "HISTORY_FILE_PATH", str(history_file))
    monkeypatch.setattr(ExegolOrchestrator, "_setup_cadence_engine", lambda self: None)
    monkeypatch.setattr(orchestrator_module.slack_manager, "setup_listener", lambda handler: None)

    restarted_orchestrator = ExegolOrchestrator()

    assert restarted_orchestrator.retry_blocked_repo(str(repo_path)) is True
    state = json.loads(state_file.read_text(encoding="utf-8"))
    assert state["status"] == "idle"
    assert state["active_agent"] is None
    assert state["retry_available"] is False


def test_retry_after_restart_allows_clean_go(tmp_path, monkeypatch):
    repo_path = tmp_path / "repo"
    exegol_dir = repo_path / ".exegol"
    exegol_dir.mkdir(parents=True)
    state_file = exegol_dir / "fleet_state.json"
    state_file.write_text(
        json.dumps({"status": "blocked", "errors": ["RuntimeError"], "retry_available": True}),
        encoding="utf-8",
    )
    priority_file = tmp_path / "priority.json"
    history_file = tmp_path / "job_history.json"
    priority_file.write_text(
        json.dumps(
            {
                "repositories": [
                    {
                        "repo_path": str(repo_path),
                        "priority": 1,
                        "agent_status": "idle",
                        "model_routing_preference": "ollama",
                    }
                ],
                "global_settings": {"context_isolation": {}, "compliance_monitoring": {}},
            }
        ),
        encoding="utf-8",
    )

    monkeypatch.setattr(orchestrator_module, "PRIORITY_FILE_PATH", str(priority_file))
    monkeypatch.setattr(orchestrator_module, "HISTORY_FILE_PATH", str(history_file))
    monkeypatch.setattr(ExegolOrchestrator, "_setup_cadence_engine", lambda self: None)
    monkeypatch.setattr(orchestrator_module.slack_manager, "setup_listener", lambda handler: None)

    restarted_orchestrator = ExegolOrchestrator()
    calls = []
    monkeypatch.setattr(restarted_orchestrator, "process_repo", lambda repo: calls.append(repo["repo_path"]))

    assert restarted_orchestrator.retry_blocked_repo(str(repo_path)) is True
    assert restarted_orchestrator.trigger_go() is True
    assert calls == [str(repo_path)]
    assert restarted_orchestrator.is_running_fleet is False


def test_start_autonomous_after_restart_is_idempotent(monkeypatch):
    class FakeThread:
        started = 0

        def __init__(self, target, daemon):
            self.target = target
            self.daemon = daemon
            self._alive = False

        def start(self):
            FakeThread.started += 1
            self._alive = True

        def is_alive(self):
            return self._alive

    monkeypatch.setattr(api.threading, "Thread", FakeThread)
    api._continuous_mode = False
    api._continuous_fleet_thread = None

    first = api.start_autonomous_fleet()
    second = api.start_autonomous_fleet()

    assert first["continuous_mode"] is True
    assert second["continuous_mode"] is True
    assert FakeThread.started == 1

    api.stop_autonomous_fleet()
    api._continuous_fleet_thread = None
