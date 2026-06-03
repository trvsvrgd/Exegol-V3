import json
import os
import sys

import pytest

os.environ["EXEGOL_DISABLE_SCHEDULER"] = "true"
os.environ["EXEGOL_DISABLE_SLACK"] = "true"
os.environ["EXEGOL_DISABLE_LOCAL_MODEL_UNLOAD"] = "true"
os.environ["SLACK_BOT_TOKEN"] = ""
os.environ["SLACK_APP_TOKEN"] = ""
os.environ["SLACK_WEBHOOK_URL"] = ""

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

import orchestrator as orchestrator_module
from handoff import SessionResult
from orchestrator import ExegolOrchestrator
from tools.backlog_manager import BacklogManager
from tools.objective_manager import ObjectiveManager
from tools.fleet_runtime_control import request_runtime_stop, resume_runtime


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
                    "context_isolation": {"max_handoff_depth": 8},
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
    resume_runtime("test setup")

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

    assert orch.retry_blocked_repo(str(repo_path)) is True
    monkeypatch.setattr(orch, "process_repo", lambda _repo_info: None)
    assert orch.run_fleet_cycle() is True
    assert orch.is_running_fleet is False


def test_run_fleet_cycle_runs_due_scheduled_before_repo_dispatch(orchestrator, monkeypatch):
    orch, repo_path, _priority_file = orchestrator
    (repo_path / "src").mkdir()
    (repo_path / "src" / "main.py").write_text("print('ready')\n", encoding="utf-8")
    events = []

    monkeypatch.setattr(
        orch,
        "run_due_scheduled_agents",
        lambda **kwargs: events.append(("due", kwargs["repo_path"], kwargs["trigger_source"])) or {"triggered_count": 1},
    )
    monkeypatch.setattr(orch, "check_compliance_monitoring", lambda: events.append(("compliance",)))
    monkeypatch.setattr(orch, "process_repo", lambda _repo_info: events.append(("process",)))

    assert orch.run_fleet_cycle(repo_path=str(repo_path), include_due_scheduled=True, trigger_source="manual_run") is True
    assert events[:3] == [
        ("due", str(repo_path), "manual_run"),
        ("compliance",),
        ("process",),
    ]


def test_run_fleet_cycle_skips_persisted_blocked_state(orchestrator, monkeypatch):
    orch, repo_path, priority_file = orchestrator
    state_file = repo_path / ".exegol" / "fleet_state.json"
    state_file.write_text(
        json.dumps(
            {
                "active_repo": str(repo_path),
                "active_agent": "developer_dex",
                "session_id": "stale123",
                "status": "blocked",
                "errors": ["Supervisor detected stale heartbeat."],
                "output_summary": "Supervisor detected stale heartbeat.",
                "blocker_type": "stale_heartbeat",
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(orch, "check_compliance_monitoring", lambda: None)
    monkeypatch.setattr(orch, "process_repo", lambda _repo_info: pytest.fail("blocked repo should not run"))

    assert orch.run_fleet_cycle(repo_path=str(repo_path)) is False
    state = json.loads(state_file.read_text(encoding="utf-8"))
    config = json.loads(priority_file.read_text(encoding="utf-8"))
    assert state["status"] == "blocked"
    assert state["blocker_type"] == "stale_heartbeat"
    assert config["repositories"][0]["agent_status"] == "blocked"


def test_run_fleet_cycle_auto_dispatches_agent_crash_backlog(orchestrator, monkeypatch):
    orch, repo_path, _priority_file = orchestrator
    failure_task_id = "auto_fail_architect_artoo_deadbeef"
    BacklogManager(str(repo_path)).add_task({
        "id": failure_task_id,
        "summary": "FIX: architect_artoo autonomous failure",
        "priority": "high",
        "type": "bug",
        "status": "todo",
        "source_agent": "FleetLogger",
        "rationale": "Traceback from architect_artoo.",
        "created_at": "2026-05-31T12:42:06",
    })
    (repo_path / ".exegol" / "fleet_state.json").write_text(
        json.dumps(
            {
                "active_repo": str(repo_path),
                "active_agent": "architect_artoo",
                "session_id": "crash123",
                "status": "blocked",
                "errors": ["KeyError: slice(None, 12, None)"],
                "output_summary": "Agent execution failed: KeyError",
                "backlog_item_id": failure_task_id,
                "retry_available": True,
            }
        ),
        encoding="utf-8",
    )
    dispatched = []

    def fake_wake(repo_info, routing, max_steps, agent_id=None, **kwargs):
        dispatched.append((repo_info["repo_path"], agent_id))
        return SessionResult(agent_id=agent_id, session_id="poe123", outcome="success")

    monkeypatch.setattr(orch, "check_compliance_monitoring", lambda: None)
    monkeypatch.setattr(orch, "wake_and_execute_agent", fake_wake)

    assert orch.run_fleet_cycle(repo_path=str(repo_path)) is True
    assert dispatched == [(os.path.abspath(repo_path), "product_poe")]

    task = BacklogManager(str(repo_path)).get_task(failure_task_id)
    assert task["priority"] == "critical"
    assert task["blocker_type"] == "agent_crash"
    assert task["auto_recovery_attempts"] == 1

    state = json.loads((repo_path / ".exegol" / "fleet_state.json").read_text(encoding="utf-8"))
    assert state["status"] != "blocked"


def test_run_fleet_cycle_skips_agent_crash_after_recovery_budget(orchestrator, monkeypatch):
    orch, repo_path, priority_file = orchestrator
    failure_task_id = "auto_fail_architect_artoo_deadbeef"
    BacklogManager(str(repo_path)).add_task({
        "id": failure_task_id,
        "summary": "FIX: architect_artoo autonomous failure",
        "priority": "critical",
        "type": "bug",
        "status": "todo",
        "source_agent": "FleetLogger",
        "rationale": "Traceback from architect_artoo.",
        "created_at": "2026-05-31T12:42:06",
        "auto_recovery_attempts": 1,
    })
    (repo_path / ".exegol" / "fleet_state.json").write_text(
        json.dumps(
            {
                "active_repo": str(repo_path),
                "active_agent": "architect_artoo",
                "session_id": "crash123",
                "status": "blocked",
                "errors": ["KeyError: slice(None, 12, None)"],
                "output_summary": "Agent execution failed: KeyError",
                "backlog_item_id": failure_task_id,
                "retry_available": True,
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(orch, "check_compliance_monitoring", lambda: None)
    monkeypatch.setattr(orch, "process_repo", lambda _repo_info: pytest.fail("recovery budget should block dispatch"))

    assert orch.run_fleet_cycle(repo_path=str(repo_path)) is False
    config = json.loads(priority_file.read_text(encoding="utf-8"))
    assert config["repositories"][0]["agent_status"] == "blocked"


def test_run_fleet_cycle_rejects_overlapping_cycle(orchestrator, monkeypatch):
    orch, _repo_path, _priority_file = orchestrator
    monkeypatch.setattr(orch, "process_repo", lambda _repo_info: pytest.fail("overlap should not process repos"))

    assert orch._fleet_cycle_lock.acquire(blocking=False) is True
    try:
        assert orch.run_fleet_cycle() is False
        assert orch.is_running_fleet is False
    finally:
        orch._fleet_cycle_lock.release()


def test_stop_request_suppresses_autonomous_handoff(orchestrator, monkeypatch):
    orch, repo_path, _priority_file = orchestrator
    calls = []

    def fake_inner(repo_info, routing, max_steps, agent_id, *args, **kwargs):
        calls.append(agent_id)
        orch.request_fleet_stop("unit test stop")
        return SessionResult(
            agent_id=agent_id,
            session_id="poe123",
            outcome="success",
            next_agent_id="developer_dex",
        )

    monkeypatch.setattr(orch, "load_cached_session_context", lambda _path: {})
    monkeypatch.setattr(orch, "cache_session_context", lambda _path, _result: None)
    monkeypatch.setattr(orch, "_wake_and_execute_agent_inner", fake_inner)

    try:
        result = orch.wake_and_execute_agent(
            {"repo_path": str(repo_path), "model_routing_preference": "ollama"},
            "ollama",
            10,
            "product_poe",
        )
    finally:
        orch.clear_fleet_stop_request()

    assert calls == ["product_poe"]
    assert result.next_agent_id == ""
    assert result.status_update == "idle"


def test_stop_request_abandons_queued_agent_wake(orchestrator):
    orch, _repo_path, _priority_file = orchestrator
    orch.current_running_agent = {"id": "held", "agent_id": "developer_dex"}

    try:
        orch.request_fleet_stop("unit test queued stop")
        acquired = orch.acquire_execution_lock("product_poe")
    finally:
        orch.current_running_agent = None
        orch.clear_fleet_stop_request()
        resume_runtime("test cleanup")

    assert acquired is False
    assert orch.pending_tasks == []


def test_scheduled_task_skips_when_runtime_stopped(orchestrator):
    orch, _repo_path, _priority_file = orchestrator
    request_runtime_stop("unit test scheduler stop")

    try:
        result = orch._run_scheduled_task(
            agent_id="product_poe",
            summary="Should not run while stopped",
            job_id="unit_job",
        )
    finally:
        resume_runtime("test cleanup")

    assert result["status"] == "skipped"
    assert result["reason"] == "fleet runtime stopped"


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


def test_retry_blocked_repo_clears_stale_heartbeat_file(orchestrator):
    orch, repo_path, _priority_file = orchestrator
    state_file = repo_path / ".exegol" / "fleet_state.json"
    heartbeat_dir = repo_path / ".exegol" / "heartbeats"
    heartbeat_dir.mkdir(parents=True, exist_ok=True)
    heartbeat_file = heartbeat_dir / "stale123.json"
    heartbeat_file.write_text(
        json.dumps(
            {
                "session_id": "stale123",
                "agent_id": "watcher_wedge",
                "status": "active",
                "last_pulse": "2026-05-01T00:00:00",
            }
        ),
        encoding="utf-8",
    )
    second_heartbeat = heartbeat_dir / "stale456.json"
    second_heartbeat.write_text(
        json.dumps(
            {
                "session_id": "stale456",
                "agent_id": "vibe_vader",
                "status": "zombie",
                "last_pulse": "2026-05-01T00:00:00",
            }
        ),
        encoding="utf-8",
    )
    acknowledged_heartbeat = heartbeat_dir / "stale789.json"
    acknowledged_heartbeat.write_text(
        json.dumps(
            {
                "session_id": "stale789",
                "agent_id": "quality_quigon",
                "status": "stale",
                "last_pulse": "2026-05-01T00:00:00",
            }
        ),
        encoding="utf-8",
    )
    state_file.write_text(
        json.dumps(
            {
                "active_repo": str(repo_path),
                "active_agent": "watcher_wedge",
                "session_id": "stale123",
                "status": "blocked",
                "errors": ["Supervisor detected stale heartbeat."],
                "output_summary": "Supervisor detected stale heartbeat.",
                "blocker_type": "stale_heartbeat",
            }
        ),
        encoding="utf-8",
    )

    assert orch.retry_blocked_repo(str(repo_path)) is True

    heartbeat = json.loads(heartbeat_file.read_text(encoding="utf-8"))
    second = json.loads(second_heartbeat.read_text(encoding="utf-8"))
    acknowledged = json.loads(acknowledged_heartbeat.read_text(encoding="utf-8"))
    assert heartbeat["status"] == "cleared"
    assert second["status"] == "cleared"
    assert acknowledged["status"] == "cleared"
    assert heartbeat["clear_reason"] == "Cleared from Workbench retry control."


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


def test_objective_idle_dispatches_planning_before_backlog(orchestrator, monkeypatch):
    orch, repo_path, _priority_file = orchestrator
    ObjectiveManager(str(repo_path)).create_or_update(goal="Ship the objective loop")
    (repo_path / ".exegol" / "backlog.json").write_text(
        json.dumps([{"id": "generic", "status": "todo", "summary": "Generic backlog work"}]),
        encoding="utf-8",
    )
    calls = []

    def fake_wake(repo_info, routing, max_steps, agent_id=None, **kwargs):
        calls.append((repo_info["repo_path"], routing, max_steps, agent_id))
        return SessionResult(
            agent_id=agent_id,
            session_id="planning123",
            outcome="success",
            output_summary="Planned objective work.",
        )

    monkeypatch.setattr(orch, "wake_and_execute_agent", fake_wake)

    orch.process_repo(orch._repo_info_for_path(str(repo_path)))

    assert calls == [(os.path.abspath(repo_path), "ollama", 10, "product_poe")]
    objective = ObjectiveManager(str(repo_path)).load()
    assert objective["phase"] == "implementing"
    assert objective["last_agent_id"] == "product_poe"
    assert objective["last_result"]["outcome"] == "success"


def test_objective_implementing_dispatches_developer_dex(orchestrator, monkeypatch):
    orch, repo_path, _priority_file = orchestrator
    manager = ObjectiveManager(str(repo_path))
    manager.create_or_update(goal="Ship the objective loop")
    manager.transition("planning")
    manager.transition("implementing", active_task_id="objective_loop_dispatch")
    calls = []

    def fake_wake(repo_info, routing, max_steps, agent_id=None, **kwargs):
        calls.append((max_steps, agent_id))
        return SessionResult(
            agent_id=agent_id,
            session_id="dex123",
            outcome="success",
            output_summary="Implemented objective slice.",
        )

    monkeypatch.setattr(orch, "wake_and_execute_agent", fake_wake)

    orch.process_repo(orch._repo_info_for_path(str(repo_path)))

    assert calls == [(15, "developer_dex")]
    objective = ObjectiveManager(str(repo_path)).load()
    assert objective["phase"] == "validating"
    assert objective["last_agent_id"] == "developer_dex"


def test_empty_objective_falls_back_to_backlog_dispatch(orchestrator, monkeypatch):
    orch, repo_path, _priority_file = orchestrator
    ObjectiveManager(str(repo_path)).load()
    (repo_path / ".exegol" / "backlog.json").write_text(
        json.dumps([{"id": "generic", "status": "todo", "summary": "Generic backlog work"}]),
        encoding="utf-8",
    )
    calls = []

    def fake_wake(repo_info, routing, max_steps, agent_id=None, **kwargs):
        calls.append((max_steps, agent_id))
        return SessionResult(agent_id=agent_id, session_id="poe123", outcome="success")

    monkeypatch.setattr(orch, "wake_and_execute_agent", fake_wake)

    orch.process_repo(orch._repo_info_for_path(str(repo_path)))

    assert calls == [(10, "product_poe")]


def test_seeded_objective_advances_to_done_across_fleet_cycles(orchestrator, monkeypatch):
    orch, repo_path, _priority_file = orchestrator
    ObjectiveManager(str(repo_path)).create_or_update(
        goal="Make Run Autonomous Fleet production ready",
        success_criteria=["planning completed", "implementation completed", "validation completed"],
        constraints=["deterministic local test only"],
    )
    dispatched = []

    def fake_wake(repo_info, routing, max_steps, agent_id=None, **kwargs):
        dispatched.append(agent_id)
        return SessionResult(
            agent_id=agent_id,
            session_id=f"{agent_id}-session",
            outcome="success",
            output_summary=f"{agent_id} completed objective phase.",
        )

    monkeypatch.setattr(orch, "check_compliance_monitoring", lambda: None)
    monkeypatch.setattr(orch, "wake_and_execute_agent", fake_wake)

    assert orch.run_fleet_cycle(repo_path=str(repo_path)) is True
    assert ObjectiveManager(str(repo_path)).load()["phase"] == "implementing"

    assert orch.run_fleet_cycle(repo_path=str(repo_path)) is True
    assert ObjectiveManager(str(repo_path)).load()["phase"] == "validating"

    assert orch.run_fleet_cycle(repo_path=str(repo_path)) is True
    assert ObjectiveManager(str(repo_path)).load()["phase"] == "accepting"

    assert orch.run_fleet_cycle(repo_path=str(repo_path)) is True
    objective = ObjectiveManager(str(repo_path)).load()

    assert dispatched == ["product_poe", "developer_dex", "quality_quigon", "uat_ulic"]
    assert objective["phase"] == "done"
    assert objective["status"] == "done"
    assert objective["last_agent_id"] == "uat_ulic"
    assert objective["last_result"]["outcome"] == "success"

    events = (repo_path / ".exegol" / "objective_events.jsonl").read_text(encoding="utf-8").splitlines()
    assert any('"phase": "done"' in event for event in events)


def test_objective_implementation_failure_transitions_to_retrying(orchestrator, monkeypatch):
    orch, repo_path, _priority_file = orchestrator
    manager = ObjectiveManager(str(repo_path))
    manager.create_or_update(goal="Recover from implementation failure")
    manager.transition("planning")
    manager.transition("implementing", active_task_id="objective_loop_verification")

    def fake_wake(repo_info, routing, max_steps, agent_id=None, **kwargs):
        return SessionResult(
            agent_id=agent_id,
            session_id="dex-failed",
            outcome="failure",
            output_summary="Patch failed validation before write.",
            errors=["synthetic implementation failure"],
        )

    monkeypatch.setattr(orch, "wake_and_execute_agent", fake_wake)

    orch.process_repo(orch._repo_info_for_path(str(repo_path)))

    objective = ObjectiveManager(str(repo_path)).load()
    assert objective["phase"] == "retrying"
    assert objective["status"] == "running"
    assert objective["last_agent_id"] == "developer_dex"
    assert objective["last_result"]["errors"] == ["synthetic implementation failure"]


def test_objective_uat_failure_transitions_to_retrying_without_global_block(orchestrator, monkeypatch):
    orch, repo_path, priority_file = orchestrator
    manager = ObjectiveManager(str(repo_path))
    manager.create_or_update(goal="Recover from UAT failure")
    manager.transition("planning")
    manager.transition("implementing", active_task_id="objective_loop_verification")
    manager.transition("validating")
    manager.transition("accepting")

    def fake_wake(repo_info, routing, max_steps, agent_id=None, **kwargs):
        return SessionResult(
            agent_id=agent_id,
            session_id="uat-failed",
            outcome="failure",
            output_summary="UAT acceptance gaps found.",
            errors=["missing restart control"],
        )

    monkeypatch.setattr(orch, "wake_and_execute_agent", fake_wake)

    orch.process_repo(orch._repo_info_for_path(str(repo_path)))

    objective = ObjectiveManager(str(repo_path)).load()
    config = json.loads(priority_file.read_text(encoding="utf-8"))
    state = json.loads((repo_path / ".exegol" / "fleet_state.json").read_text(encoding="utf-8"))
    assert objective["phase"] == "retrying"
    assert objective["status"] == "running"
    assert objective["last_agent_id"] == "uat_ulic"
    assert objective["last_result"]["errors"] == ["missing restart control"]
    assert config["repositories"][0]["agent_status"] == "idle"
    assert state["status"] == "running"
    assert "Retrying with developer_dex" in state["output_summary"]


def test_objective_planning_failure_records_environment_blocker(orchestrator, monkeypatch):
    orch, repo_path, _priority_file = orchestrator
    ObjectiveManager(str(repo_path)).create_or_update(goal="Recover from planning failure")

    def fake_wake(repo_info, routing, max_steps, agent_id=None, **kwargs):
        return SessionResult(
            agent_id=agent_id,
            session_id="poe-failed",
            outcome="failure",
            output_summary="Provider unavailable during planning.",
            errors=["provider unavailable"],
        )

    monkeypatch.setattr(orch, "wake_and_execute_agent", fake_wake)

    orch.process_repo(orch._repo_info_for_path(str(repo_path)))

    objective = ObjectiveManager(str(repo_path)).load()
    assert objective["phase"] == "blocked_environment"
    assert objective["status"] == "blocked"
    assert objective["blocked_reason"] == "provider unavailable"
    assert objective["last_agent_id"] == "product_poe"
