import os
import sys
import time

import pytest
from fastapi.testclient import TestClient

os.environ["SLACK_BOT_TOKEN"] = ""
os.environ["SLACK_APP_TOKEN"] = ""
os.environ["SLACK_WEBHOOK_URL"] = ""
os.environ["EXEGOL_DISABLE_SCHEDULER"] = "true"
os.environ["EXEGOL_DISABLE_LOCAL_MODEL_UNLOAD"] = "true"

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

import api
from tools.objective_manager import ObjectiveManager
from tools.fleet_runtime_control import is_runtime_stopped, request_runtime_stop, resume_runtime


def test_start_autonomous_is_idempotent(monkeypatch):
    api.stop_autonomous_fleet()

    calls = []

    def fake_run_fleet_cycle(repo_path=None, include_due_scheduled=False, trigger_source="manual_run"):
        calls.append(time.time())
        return True

    monkeypatch.setattr(api.orchestrator, "run_fleet_cycle", fake_run_fleet_cycle)

    first = api.start_autonomous_fleet()
    first_thread = api._continuous_fleet_thread
    second = api.start_autonomous_fleet()

    try:
        assert first["continuous_mode"] is True
        assert second["continuous_mode"] is True
        assert first_thread is api._continuous_fleet_thread
    finally:
        api.stop_autonomous_fleet()


def test_start_autonomous_records_selected_repo(monkeypatch, tmp_path):
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
    api._continuous_repo_path = None
    api._continuous_fleet_thread = None

    first = api.start_autonomous_fleet(api.RepoRequest(repo_path=str(tmp_path)))
    second = api.start_autonomous_fleet(api.RepoRequest(repo_path=str(tmp_path)))

    assert first["continuous_mode"] is True
    assert first["repo_path"] == os.path.abspath(tmp_path)
    assert second["repo_path"] == os.path.abspath(tmp_path)
    assert FakeThread.started == 1

    api.stop_autonomous_fleet()
    api._continuous_fleet_thread = None


def test_start_autonomous_resumes_stopped_runtime(monkeypatch, tmp_path):
    class FakeThread:
        def __init__(self, target, daemon):
            self.target = target
            self.daemon = daemon
            self._alive = False

        def start(self):
            self._alive = True

        def is_alive(self):
            return self._alive

    monkeypatch.setattr(api.threading, "Thread", FakeThread)
    request_runtime_stop("unit test stop")
    api._continuous_mode = False
    api._continuous_repo_path = None
    api._continuous_fleet_thread = None

    try:
        status = api.start_autonomous_fleet(api.RepoRequest(repo_path=str(tmp_path)))
        assert status["continuous_mode"] is True
        assert is_runtime_stopped() is False
    finally:
        api.stop_autonomous_fleet()
        api._continuous_fleet_thread = None
        resume_runtime("test cleanup")


def test_continuous_loop_runs_selected_repo(monkeypatch, tmp_path):
    calls = []

    def fake_run_fleet_cycle(repo_path=None, include_due_scheduled=False, trigger_source="manual_run"):
        calls.append((repo_path, include_due_scheduled, trigger_source))
        with api._continuous_lock:
            api._continuous_mode = False
        return True

    monkeypatch.setattr(api.orchestrator, "run_fleet_cycle", fake_run_fleet_cycle)
    api._continuous_mode = True
    api._continuous_repo_path = os.path.abspath(tmp_path)

    api._continuous_fleet_loop()

    assert calls == [(os.path.abspath(tmp_path), True, "manual_run")]


def test_continuous_loop_runs_multiple_cycles_until_stopped(monkeypatch, tmp_path):
    calls = []

    def fake_run_fleet_cycle(repo_path=None, include_due_scheduled=False, trigger_source="manual_run"):
        calls.append((repo_path, include_due_scheduled, trigger_source))
        if len(calls) == 2:
            with api._continuous_lock:
                api._continuous_mode = False
        return True

    monkeypatch.setattr(api.orchestrator, "run_fleet_cycle", fake_run_fleet_cycle)
    monkeypatch.setattr(api.time, "sleep", lambda _seconds: None)
    api._continuous_mode = True
    api._continuous_repo_path = os.path.abspath(tmp_path)

    api._continuous_fleet_loop()

    assert calls == [
        (os.path.abspath(tmp_path), True, "manual_run"),
        (os.path.abspath(tmp_path), True, "manual_run"),
    ]


def test_continuous_loop_stops_selected_repo_when_objective_done(monkeypatch, tmp_path):
    repo_path = os.path.abspath(tmp_path)
    manager = ObjectiveManager(repo_path)
    manager.create_or_update(goal="Complete selected objective")
    manager.transition("planning")
    calls = []

    def complete_objective(repo_path=None, include_due_scheduled=False, trigger_source="manual_run"):
        calls.append((repo_path, include_due_scheduled, trigger_source))
        manager.transition("implementing")
        manager.transition("validating")
        manager.transition("accepting")
        manager.transition("done")
        return True

    monkeypatch.setattr(api.orchestrator, "run_fleet_cycle", complete_objective)
    monkeypatch.setattr(api.time, "sleep", lambda _seconds: pytest.fail("done objective should not sleep before stopping"))
    api._continuous_mode = True
    api._continuous_repo_path = repo_path
    api._continuous_cycle_active = False

    api._continuous_fleet_loop()

    assert calls == [(repo_path, True, "manual_run")]
    assert api._continuous_mode is False
    assert api._continuous_repo_path is None
    assert api._continuous_cycle_active is False


def test_autonomous_status_reports_stopping_until_cycle_unwinds(tmp_path):
    repo_path = os.path.abspath(tmp_path)
    api._continuous_mode = False
    api._continuous_repo_path = repo_path
    api._continuous_fleet_thread = None
    api._continuous_cycle_active = True
    api.orchestrator.is_running_fleet = False

    try:
        status = api._autonomous_status()
        context = api._autonomous_context_for_repo(repo_path)
    finally:
        api._continuous_cycle_active = False
        api._continuous_repo_path = None

    assert status["continuous_mode"] is False
    assert status["cycle_running"] is True
    assert status["stopping"] is True
    assert context["loop_status"] == "stopping"


def test_stop_autonomous_requests_cooperative_orchestrator_stop(tmp_path):
    repo_path = os.path.abspath(tmp_path)
    api.orchestrator.clear_fleet_stop_request()
    api._continuous_mode = True
    api._continuous_repo_path = repo_path
    api._continuous_fleet_thread = None
    api._continuous_cycle_active = True
    api.orchestrator.is_running_fleet = True

    try:
        status = api.stop_autonomous_fleet()

        assert status["status"] == "success"
        assert status["continuous_mode"] is False
        assert status["cycle_running"] is True
        assert status["stopping"] is True
        assert status["repo_path"] is None
        assert api.orchestrator.is_fleet_stop_requested()
    finally:
        api._continuous_cycle_active = False
        api._continuous_repo_path = None
        api.orchestrator.is_running_fleet = False
        api.orchestrator.clear_fleet_stop_request()


def test_stop_autonomous_stops_objective_loops_and_pauses_runtime(tmp_path):
    repo_path = os.path.abspath(tmp_path)
    stop_event = api.threading.Event()
    with api._objective_loops_lock:
        api._active_objective_loops[repo_path] = {
            "event": stop_event,
            "thread": type("ThreadStub", (), {"is_alive": lambda self: True})(),
            "started_at": "2026-06-02T00:00:00",
        }
    api._continuous_mode = True
    api._continuous_repo_path = repo_path
    api._continuous_fleet_thread = None
    api._continuous_cycle_active = False

    try:
        status = api.stop_autonomous_fleet()

        assert status["status"] == "success"
        assert status["objective_loops_stopped"] == 1
        assert stop_event.is_set()
        assert is_runtime_stopped() is True
        with api._objective_loops_lock:
            assert repo_path not in api._active_objective_loops
    finally:
        api._continuous_mode = False
        api._continuous_repo_path = None
        api.orchestrator.clear_fleet_stop_request()
        resume_runtime("test cleanup")


def test_start_autonomous_http_uses_selected_repo(monkeypatch, tmp_path):
    class FakeThread:
        def __init__(self, target, daemon):
            self.target = target
            self.daemon = daemon
            self._alive = False

        def start(self):
            self._alive = True

        def is_alive(self):
            return self._alive

    monkeypatch.setattr(api.threading, "Thread", FakeThread)
    api._continuous_mode = False
    api._continuous_repo_path = None
    api._continuous_fleet_thread = None

    client = TestClient(api.app)
    response = client.post(
        "/fleet/start-autonomous",
        json={"repo_path": str(tmp_path)},
        headers={"X-API-Key": os.getenv("EXEGOL_API_KEY", "dev-local-key")},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "success"
    assert body["continuous_mode"] is True
    assert body["repo_path"] == os.path.abspath(tmp_path)

    api.stop_autonomous_fleet()
    api._continuous_fleet_thread = None


def test_active_state_reconciles_stale_heartbeat(monkeypatch, tmp_path):
    repo_path = tmp_path / "repo"
    heartbeat_dir = repo_path / ".exegol" / "heartbeats"
    heartbeat_dir.mkdir(parents=True)
    heartbeat_file = heartbeat_dir / "stale123.json"
    heartbeat_file.write_text(
        """
        {
          "session_id": "stale123",
          "agent_id": "developer_dex",
          "status": "zombie",
          "last_pulse": "2026-05-01T00:00:00"
        }
        """,
        encoding="utf-8",
    )
    monkeypatch.setattr(api.orchestrator, "load_config", lambda: None)
    monkeypatch.setattr(
        api.orchestrator,
        "priority_config",
        {"repositories": [{"repo_path": str(repo_path), "agent_status": "idle"}]},
    )
    api._continuous_mode = True
    api._continuous_repo_path = os.path.abspath(repo_path)
    api.orchestrator.is_running_fleet = False

    try:
        state = api.get_fleet_active_state(str(repo_path))
    finally:
        api._continuous_mode = False
        api._continuous_repo_path = None

    assert state["status"] == "blocked"
    assert state["active_agent"] == "developer_dex"
    assert state["session_id"] == "stale123"
    assert state["blocker_type"] == "stale_heartbeat"
    assert state["autonomous"]["loop_status"] == "waiting_between_cycles"
