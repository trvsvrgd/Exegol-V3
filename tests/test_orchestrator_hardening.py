import json
import os
import sys

import pytest

os.environ["EXEGOL_DISABLE_SCHEDULER"] = "true"
os.environ["EXEGOL_DISABLE_SLACK"] = "true"
os.environ["SLACK_BOT_TOKEN"] = ""
os.environ["SLACK_APP_TOKEN"] = ""
os.environ["SLACK_WEBHOOK_URL"] = ""

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

import orchestrator as orchestrator_module
from orchestrator import ExegolOrchestrator


@pytest.fixture
def orchestrator(tmp_path, monkeypatch):
    repo_path = tmp_path / "repo"
    exegol_dir = repo_path / ".exegol"
    exegol_dir.mkdir(parents=True)

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
                "global_settings": {
                    "context_isolation": {"max_handoff_depth": 5},
                    "compliance_monitoring": {},
                },
            }
        ),
        encoding="utf-8",
    )

    monkeypatch.setattr(orchestrator_module, "PRIORITY_FILE_PATH", str(priority_file))
    monkeypatch.setattr(orchestrator_module, "HISTORY_FILE_PATH", str(history_file))
    monkeypatch.setattr(ExegolOrchestrator, "_setup_cadence_engine", lambda self: None)
    monkeypatch.setattr(orchestrator_module.slack_manager, "setup_listener", lambda handler: None)
    monkeypatch.setattr(orchestrator_module.slack_manager, "post_message", lambda *args, **kwargs: None)

    orch = ExegolOrchestrator()
    return orch, repo_path, priority_file


def test_run_fleet_cycle_resets_running_flag_after_exception(orchestrator, monkeypatch):
    orch, repo_path, priority_file = orchestrator

    monkeypatch.setattr(orch, "check_compliance_monitoring", lambda: None)

    def fail_process(_repo_info):
        raise RuntimeError("boom")

    monkeypatch.setattr(orch, "process_repo", fail_process)

    assert orch.run_fleet_cycle() is False
    assert orch.is_running_fleet is False
    state = json.loads((repo_path / ".exegol" / "fleet_state.json").read_text(encoding="utf-8"))
    assert state["status"] == "blocked"
    assert state["active_agent"] == "orchestrator"
    assert "RuntimeError: boom" in state["errors"][0]

    config = json.loads(priority_file.read_text(encoding="utf-8"))
    assert config["repositories"][0]["agent_status"] == "blocked"
    config["repositories"][0]["agent_status"] = "idle"
    priority_file.write_text(json.dumps(config), encoding="utf-8")
    orch.load_config()

    monkeypatch.setattr(orch, "process_repo", lambda _repo_info: None)
    assert orch.run_fleet_cycle() is True
    assert orch.is_running_fleet is False


def test_run_fleet_cycle_rejects_overlapping_cycle(orchestrator, monkeypatch):
    orch, _repo_path, _priority_file = orchestrator
    monkeypatch.setattr(orch, "process_repo", lambda _repo_info: pytest.fail("overlap should not process repos"))

    assert orch._fleet_cycle_lock.acquire(blocking=False) is True
    try:
        assert orch.run_fleet_cycle() is False
        assert orch.is_running_fleet is False
    finally:
        orch._fleet_cycle_lock.release()


def test_retry_blocked_repo_moves_config_and_state_to_idle(orchestrator):
    orch, repo_path, priority_file = orchestrator
    state_file = repo_path / ".exegol" / "fleet_state.json"
    state_file.write_text(
        json.dumps(
            {
                "active_repo": str(repo_path),
                "active_agent": "architect_artoo",
                "session_id": "abc123",
                "status": "blocked",
                "errors": ["KeyError"],
                "output_summary": "Agent execution failed.",
            }
        ),
        encoding="utf-8",
    )

    config = json.loads(priority_file.read_text(encoding="utf-8"))
    config["repositories"][0]["agent_status"] = "blocked"
    priority_file.write_text(json.dumps(config), encoding="utf-8")

    assert orch.retry_blocked_repo(str(repo_path)) is True

    updated_config = json.loads(priority_file.read_text(encoding="utf-8"))
    assert updated_config["repositories"][0]["agent_status"] == "idle"

    updated_state = json.loads(state_file.read_text(encoding="utf-8"))
    assert updated_state["status"] == "idle"
    assert updated_state["active_agent"] is None
    assert updated_state["errors"] == []
    assert updated_state["last_cleared_errors"] == ["KeyError"]
    assert updated_state["output_summary"] == "Blocked state cleared for retry."


def test_retry_blocked_repo_clears_state_block_when_config_is_idle(orchestrator):
    orch, repo_path, _priority_file = orchestrator
    state_file = repo_path / ".exegol" / "fleet_state.json"
    state_file.write_text(
        json.dumps(
            {
                "active_repo": str(repo_path),
                "active_agent": "developer_dex",
                "session_id": "abc123",
                "status": "blocked",
                "errors": ["RuntimeError"],
                "output_summary": "Agent execution failed.",
                "retry_available": True,
            }
        ),
        encoding="utf-8",
    )

    assert orch.retry_blocked_repo(str(repo_path)) is True

    updated_state = json.loads(state_file.read_text(encoding="utf-8"))
    assert updated_state["status"] == "idle"
    assert updated_state["active_agent"] is None
    assert updated_state["retry_available"] is False


def test_trigger_go_rejects_overlap(orchestrator, monkeypatch):
    orch, _repo_path, _priority_file = orchestrator
    monkeypatch.setattr(orch, "process_repo", lambda _repo_info: pytest.fail("overlap should not process repos"))

    assert orch._fleet_cycle_lock.acquire(blocking=False) is True
    try:
        assert orch.trigger_go() is False
    finally:
        orch._fleet_cycle_lock.release()


def test_trigger_go_records_processing_failure(orchestrator, monkeypatch):
    orch, repo_path, priority_file = orchestrator

    def fail_process(_repo_info):
        raise ValueError("bad repo")

    monkeypatch.setattr(orch, "process_repo", fail_process)

    assert orch.trigger_go() is False
    assert orch.is_running_fleet is False

    state = json.loads((repo_path / ".exegol" / "fleet_state.json").read_text(encoding="utf-8"))
    assert state["status"] == "blocked"
    assert state["active_agent"] == "orchestrator"
    assert "ValueError: bad repo" in state["errors"][0]

    config = json.loads(priority_file.read_text(encoding="utf-8"))
    assert config["repositories"][0]["agent_status"] == "blocked"
