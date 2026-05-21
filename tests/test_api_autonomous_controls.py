import os
import sys
import time

from fastapi.testclient import TestClient

os.environ["SLACK_BOT_TOKEN"] = ""
os.environ["SLACK_APP_TOKEN"] = ""
os.environ["SLACK_WEBHOOK_URL"] = ""
os.environ["EXEGOL_DISABLE_SCHEDULER"] = "true"

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

import api


def test_start_autonomous_is_idempotent(monkeypatch):
    api.stop_autonomous_fleet()

    calls = []

    def fake_run_fleet_cycle():
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


def test_continuous_loop_runs_selected_repo(monkeypatch, tmp_path):
    calls = []

    def fake_run_fleet_cycle(repo_path=None):
        calls.append(repo_path)
        with api._continuous_lock:
            api._continuous_mode = False
        return True

    monkeypatch.setattr(api.orchestrator, "run_fleet_cycle", fake_run_fleet_cycle)
    api._continuous_mode = True
    api._continuous_repo_path = os.path.abspath(tmp_path)

    api._continuous_fleet_loop()

    assert calls == [os.path.abspath(tmp_path)]


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
