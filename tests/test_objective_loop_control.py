import os
import sys
import time
import pytest
import threading
from types import SimpleNamespace
from fastapi.testclient import TestClient

# Ensure src is in sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "src")))

import api
from tools.objective_manager import ObjectiveManager
from orchestrator import ExegolOrchestrator


def test_transition_to_idle_and_pausing_resuming(tmp_path):
    manager = ObjectiveManager(str(tmp_path))
    manager.create_or_update(goal="Test transition controls")
    
    # 1. Verify ALLOWED_TRANSITIONS allows transition to idle from implementing/planning/etc.
    manager.transition("planning")
    manager.transition("implementing")
    # Transition to idle from implementing
    obj = manager.transition("idle")
    assert obj["phase"] == "idle"
    assert obj["status"] == "idle"
    
    # Let's transition back to planning
    manager.transition("planning")
    # Verify we can pause planning (expected status is running, it becomes paused)
    obj = manager.pause()
    assert obj["status"] == "paused"
    
    # Verify loaded state remains paused
    loaded = manager.load()
    assert loaded["status"] == "paused"
    
    # Verify we cannot pause again
    with pytest.raises(ValueError, match="Cannot pause objective"):
        manager.pause()
        
    # Verify resume
    obj = manager.resume()
    assert obj["status"] == "running"
    assert obj["phase"] == "planning"
    
    # Verify we cannot resume again
    with pytest.raises(ValueError, match="Cannot resume objective"):
        manager.resume()


def test_chaining_suppression(monkeypatch):
    orchestrator = api.orchestrator
    
    # Create a mock agent result class
    class MockAgentResult:
        def __init__(self, outcome="success", next_agent_id=None, snapshot_hash="", regression_context=""):
            self.outcome = outcome
            self.next_agent_id = next_agent_id
            self.snapshot_hash = snapshot_hash
            self.regression_context = regression_context
            
        def to_dict(self):
            return {"outcome": self.outcome}
            
    # Mock _wake_and_execute_agent_inner to return a success with next_agent_id
    inner_calls = []
    def mock_inner(repo_info, routing, max_steps, agent_id, snapshot_hash, regression_context,
                   loop_depth, chain_history, scheduled_prompt, allow_chaining):
        inner_calls.append(agent_id)
        return MockAgentResult(outcome="success", next_agent_id="developer_dex")
        
    monkeypatch.setattr(orchestrator, "_wake_and_execute_agent_inner", mock_inner)
    
    # Case 1: allow_chaining=False
    result = orchestrator.wake_and_execute_agent(
        repo_info={"repo_path": "dummy"},
        routing="dummy_model",
        max_steps=10,
        agent_id="product_poe",
        allow_chaining=False
    )
    # It should not call itself recursively, so inner_calls should only contain "product_poe"
    assert inner_calls == ["product_poe"]
    assert result.next_agent_id == "developer_dex"
    
    inner_calls.clear()
    
    # Case 2: allow_chaining=True
    # It should call wake_and_execute_agent recursively.
    # Note: to prevent infinite recursion, we can make the second call return None or next_agent_id=None
    def mock_inner_with_stop(repo_info, routing, max_steps, agent_id, snapshot_hash, regression_context,
                             loop_depth, chain_history, scheduled_prompt, allow_chaining):
        inner_calls.append(agent_id)
        if agent_id == "product_poe":
            return MockAgentResult(outcome="success", next_agent_id="developer_dex")
        else:
            return MockAgentResult(outcome="success", next_agent_id=None)
            
    monkeypatch.setattr(orchestrator, "_wake_and_execute_agent_inner", mock_inner_with_stop)
    
    result2 = orchestrator.wake_and_execute_agent(
        repo_info={"repo_path": "dummy"},
        routing="dummy_model",
        max_steps=10,
        agent_id="product_poe",
        allow_chaining=True
    )
    assert inner_calls == ["product_poe", "developer_dex"]
    assert result2.next_agent_id is None


def test_api_objective_lifecycle(monkeypatch, tmp_path):
    # Ensure there are no active loops for our tmp repo
    repo_path = os.path.abspath(str(tmp_path))
    
    # Set up api objective file
    manager = ObjectiveManager(repo_path)
    manager.create_or_update(goal="Test loop lifecycle via API")
    manager.transition("planning")
    
    # Mock orchestrator.run_fleet_cycle to just sleep a bit and track calls
    cycle_calls = []
    def mock_run_fleet_cycle(repo_path=None):
        cycle_calls.append(repo_path)
        time.sleep(0.1)
        
    monkeypatch.setattr(api.orchestrator, "run_fleet_cycle", mock_run_fleet_cycle)
    
    client = TestClient(api.app)
    api_key = os.getenv("EXEGOL_API_KEY", "dev-local-key")
    headers = {"X-API-Key": api_key}
    
    try:
        # Check initial status
        res = client.get(f"/objective/status?repo_path={repo_path}", headers=headers)
        assert res.status_code == 200
        assert res.json()["loop_running"] is False
        assert res.json()["objective"]["phase"] == "planning"
        
        # Try starting without objective - goal exists, so it should succeed.
        res = client.post("/objective/start", json={"repo_path": repo_path}, headers=headers)
        if res.status_code != 200:
            print("FAILED START RESPONSE:", res.json())
        assert res.status_code == 200
        assert res.json()["status"] == "success"
        
        # Verify status is running
        time.sleep(0.2) # Allow thread to start and run
        res = client.get(f"/objective/status?repo_path={repo_path}", headers=headers)
        assert res.status_code == 200
        assert res.json()["loop_running"] is True
        
        # Pause the objective
        res = client.post("/objective/pause", json={"repo_path": repo_path}, headers=headers)
        assert res.status_code == 200
        assert res.json()["objective"]["status"] == "paused"
        
        # Verify status is paused
        res = client.get(f"/objective/status?repo_path={repo_path}", headers=headers)
        assert res.json()["objective"]["status"] == "paused"
        
        # Resume the objective
        res = client.post("/objective/resume", json={"repo_path": repo_path}, headers=headers)
        assert res.status_code == 200
        assert res.json()["objective"]["status"] == "running"
        
        # Stop the objective
        res = client.post("/objective/stop", json={"repo_path": repo_path}, headers=headers)
        assert res.status_code == 200
        assert res.json()["status"] == "success"
        
        # Verify stopped
        time.sleep(0.2)
        res = client.get(f"/objective/status?repo_path={repo_path}", headers=headers)
        assert res.json()["loop_running"] is False
        assert res.json()["objective"]["phase"] == "idle"
        
    finally:
        # Cleanup: force stop loop if still running
        with api._objective_loops_lock:
            if repo_path in api._active_objective_loops:
                api._active_objective_loops[repo_path]["event"].set()
                api._active_objective_loops.pop(repo_path)


def test_objective_loop_worker_stops_and_unregisters_when_objective_done(monkeypatch, tmp_path):
    repo_path = os.path.abspath(str(tmp_path))
    manager = ObjectiveManager(repo_path)
    manager.create_or_update(goal="Complete selected objective")
    manager.transition("planning")
    stop_event = threading.Event()
    calls = []

    def complete_objective(repo_path=None):
        calls.append(repo_path)
        manager.transition("implementing")
        manager.transition("validating")
        manager.transition("accepting")
        manager.transition("done")
        return True

    monkeypatch.setattr(api.orchestrator, "run_fleet_cycle", complete_objective)
    with api._objective_loops_lock:
        api._active_objective_loops[repo_path] = {
            "event": stop_event,
            "thread": SimpleNamespace(is_alive=lambda: True),
            "started_at": "2026-06-01T00:00:00",
        }

    api._objective_loop_for_repo(repo_path, stop_event)

    assert calls == [repo_path]
    assert ObjectiveManager(repo_path).load()["phase"] == "done"
    with api._objective_loops_lock:
        assert repo_path not in api._active_objective_loops
