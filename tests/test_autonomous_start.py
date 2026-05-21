import os
import hmac
import hashlib

from fastapi.testclient import TestClient

import api
from handoff import HandoffContext
from orchestrator import ExegolOrchestrator
from session_manager import SessionManager


class ImmediateExecutor:
    def submit(self, fn, *args, **kwargs):
        fn(*args, **kwargs)


def test_default_handoff_signature_is_valid_without_env_secret(monkeypatch):
    monkeypatch.delenv("EXEGOL_HMAC_SECRET", raising=False)
    handoff = HandoffContext(
        repo_path=os.getcwd(),
        agent_id="product_poe",
        task_id="fleet_cycle",
        model_routing="ollama",
        max_steps=10,
    )

    signed = ExegolOrchestrator.__new__(ExegolOrchestrator)._sign_handoff(handoff)

    assert SessionManager._validate_handoff_signature(signed)


def test_handoff_signature_honors_env_secret(monkeypatch):
    monkeypatch.setenv("EXEGOL_HMAC_SECRET", "unit-test-secret")
    handoff = HandoffContext(
        repo_path=os.getcwd(),
        agent_id="product_poe",
        task_id="fleet_cycle",
        model_routing="ollama",
        max_steps=10,
    )

    signed = ExegolOrchestrator.__new__(ExegolOrchestrator)._sign_handoff(handoff)
    data = f"{handoff.repo_path}|{handoff.agent_id}|{handoff.session_id}|{handoff.timestamp}"
    expected = hmac.new(b"unit-test-secret", data.encode(), hashlib.sha256).hexdigest()

    assert signed.signature == expected
    assert SessionManager._validate_handoff_signature(signed)


def test_autonomous_start_runs_selected_repo(monkeypatch, tmp_path):
    calls = []

    def fake_run_fleet_cycle(repo_path=None):
        calls.append(repo_path)

    monkeypatch.setattr(api, "_executor", ImmediateExecutor())
    monkeypatch.setattr(api.orchestrator, "run_fleet_cycle", fake_run_fleet_cycle)

    client = TestClient(api.app)
    response = client.post(
        "/autonomous/start",
        json={"repo_path": str(tmp_path)},
        headers={"X-API-Key": os.getenv("EXEGOL_API_KEY", "dev-local-key")},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "queued"
    assert calls == [str(tmp_path)]
    assert api._running_tasks[body["session_id"]]["status"] == "done"


def test_targeted_fleet_cycle_processes_blocked_or_unconfigured_repo(monkeypatch, tmp_path):
    orchestrator = ExegolOrchestrator.__new__(ExegolOrchestrator)
    orchestrator.priority_config = {
        "repositories": [
            {
                "repo_path": str(tmp_path),
                "priority": 20,
                "agent_status": "blocked",
                "model_routing_preference": "gemini",
            }
        ],
        "global_settings": {},
    }
    orchestrator.is_running_fleet = False

    processed = []
    monkeypatch.setattr(orchestrator, "check_compliance_monitoring", lambda: None)
    monkeypatch.setattr(orchestrator, "process_repo", lambda repo_info: processed.append(repo_info))

    orchestrator.run_fleet_cycle(repo_path=str(tmp_path))

    assert len(processed) == 1
    assert processed[0]["repo_path"] == os.path.abspath(tmp_path)
    assert processed[0]["model_routing_preference"] == "gemini"
    assert orchestrator.is_running_fleet is False
