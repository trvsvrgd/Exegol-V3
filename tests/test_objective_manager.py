import json
import os

import pytest
from fastapi.testclient import TestClient

from tools.objective_manager import ObjectiveManager


def test_load_initializes_default_objective(tmp_path):
    objective = ObjectiveManager(str(tmp_path)).load()

    assert objective["repo_path"] == os.path.abspath(tmp_path)
    assert objective["goal"] == ""
    assert objective["phase"] == "idle"
    assert objective["status"] == "idle"
    assert objective["loop_count"] == 0
    assert (tmp_path / ".exegol" / "objective.json").exists()


def test_create_or_update_persists_goal_success_criteria_and_constraints(tmp_path):
    manager = ObjectiveManager(str(tmp_path))

    objective = manager.create_or_update(
        goal="Make the launcher reliable",
        success_criteria=["Start_Exegol.bat passes", "Run Autonomous Fleet resumes objective"],
        constraints=["No external tests in deterministic suite", ""],
    )

    assert objective["goal"] == "Make the launcher reliable"
    assert objective["phase"] == "idle"
    assert objective["status"] == "idle"
    assert objective["success_criteria"] == [
        "Start_Exegol.bat passes",
        "Run Autonomous Fleet resumes objective",
    ]
    assert objective["constraints"] == ["No external tests in deterministic suite"]


def test_load_migrates_partial_objective(tmp_path):
    objective_path = tmp_path / ".exegol" / "objective.json"
    objective_path.parent.mkdir()
    objective_path.write_text(json.dumps({"goal": "Finish objective loop", "phase": "nonsense"}), encoding="utf-8")

    objective = ObjectiveManager(str(tmp_path)).load()

    assert objective["goal"] == "Finish objective loop"
    assert objective["phase"] == "idle"
    assert objective["status"] == "idle"
    assert "id" in objective
    assert "success_criteria" in objective


def test_transition_validates_state_and_writes_events(tmp_path):
    manager = ObjectiveManager(str(tmp_path))
    manager.create_or_update(goal="Ship objective loop")

    planning = manager.transition("planning", active_task_id="objective_loop_state_machine")
    objective = manager.transition("implementing", last_agent_id="developer_dex", last_result={"outcome": "started"})

    assert planning["phase"] == "planning"
    assert objective["phase"] == "implementing"
    assert objective["status"] == "running"
    assert objective["loop_count"] == 2
    events = (tmp_path / ".exegol" / "objective_events.jsonl").read_text(encoding="utf-8").splitlines()
    assert any('"event_type": "objective_transition"' in line for line in events)

    with pytest.raises(ValueError):
        manager.transition("unknown")


def test_state_machine_rejects_illegal_skip_and_mismatched_status(tmp_path):
    manager = ObjectiveManager(str(tmp_path))
    manager.create_or_update(goal="Ship objective loop")

    with pytest.raises(ValueError, match="idle -> validating"):
        manager.transition("validating")

    with pytest.raises(ValueError, match="requires status"):
        manager.transition("planning", status="blocked")


def test_blocked_transitions_require_reason_and_terminal_states_clear_active_task(tmp_path):
    manager = ObjectiveManager(str(tmp_path))
    manager.create_or_update(goal="Ship objective loop")
    manager.transition("planning", active_task_id="task-1")

    with pytest.raises(ValueError, match="blocked_reason"):
        manager.transition("blocked_human")

    blocked = manager.transition("blocked_human", blocked_reason="Need API key")
    assert blocked["status"] == "blocked"
    assert blocked["blocked_reason"] == "Need API key"

    resumed = manager.transition("planning")
    assert resumed["blocked_reason"] is None

    done = manager.transition("implementing", active_task_id="task-1")
    done = manager.transition("validating")
    done = manager.transition("accepting")
    done = manager.transition("done")
    assert done["status"] == "done"
    assert done["active_task_id"] is None


def test_objective_api_get_initializes_and_post_updates(tmp_path):
    import api

    client = TestClient(api.app)
    headers = {"X-API-Key": os.getenv("EXEGOL_API_KEY", "dev-local-key")}

    get_response = client.get(
        f"/objective?repo_path={str(tmp_path)}",
        headers=headers,
    )
    assert get_response.status_code == 200
    assert get_response.json()["phase"] == "idle"

    post_response = client.post(
        "/objective",
        json={
            "repo_path": str(tmp_path),
            "goal": "Create a reliable loop",
            "success_criteria": ["Objective reaches done"],
            "constraints": ["Stay local-first"],
        },
        headers=headers,
    )

    assert post_response.status_code == 200
    body = post_response.json()
    assert body["goal"] == "Create a reliable loop"
    assert body["phase"] == "idle"


def test_objective_api_rejects_blank_goal(tmp_path):
    import api

    client = TestClient(api.app)
    response = client.post(
        "/objective",
        json={"repo_path": str(tmp_path), "goal": "   "},
        headers={"X-API-Key": os.getenv("EXEGOL_API_KEY", "dev-local-key")},
    )

    assert response.status_code == 400


def test_objective_transition_api_applies_state_machine(tmp_path):
    import api

    client = TestClient(api.app)
    headers = {"X-API-Key": os.getenv("EXEGOL_API_KEY", "dev-local-key")}
    client.post(
        "/objective",
        json={"repo_path": str(tmp_path), "goal": "Create a reliable loop"},
        headers=headers,
    )

    ok = client.post(
        "/objective/transition",
        json={"repo_path": str(tmp_path), "phase": "planning", "active_task_id": "task-1"},
        headers=headers,
    )
    assert ok.status_code == 200
    assert ok.json()["phase"] == "planning"

    conflict = client.post(
        "/objective/transition",
        json={"repo_path": str(tmp_path), "phase": "done"},
        headers=headers,
    )
    assert conflict.status_code == 409
