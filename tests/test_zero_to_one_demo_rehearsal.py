import json
import os

import pytest
from fastapi.testclient import TestClient

import api
import orchestrator as orchestrator_module
from orchestrator import ExegolOrchestrator
from tools.hitl_manager import HITLManager
from tools.objective_manager import ObjectiveManager
from tools.thrawn_intel_manager import ThrawnIntelManager
from tools.zero_to_one_onboarding import VADER_BOUNDARY_TASK


os.environ["EXEGOL_DISABLE_SCHEDULER"] = "true"
os.environ["EXEGOL_DISABLE_SLACK"] = "true"
os.environ["SLACK_BOT_TOKEN"] = ""
os.environ["SLACK_APP_TOKEN"] = ""
os.environ["SLACK_WEBHOOK_URL"] = ""


class DemoLLM:
    model = "demo-local"

    def generate(self, prompt, system_instruction=None, json_format=False):
        # ProductPoe HITL salvage receives a harmless empty list. DeveloperDex
        # receives malformed planning JSON so the zero-to-one fallback is proven.
        if "salvageable_ids" in prompt:
            return "[]"
        return "not json"

    def generate_system_prompt(self, agent):
        return f"Demo prompt for {getattr(agent, 'name', agent.__class__.__name__)}"


@pytest.mark.parametrize("trial_index", range(3))
def test_fresh_repo_register_hitl_and_builds_playable_game(tmp_path, monkeypatch, trial_index):
    repo_path = tmp_path / f"fresh_game_repo_{trial_index}"
    (repo_path / ".git").mkdir(parents=True)
    priority_file = tmp_path / "priority.json"
    history_file = tmp_path / "job_history.json"
    priority_file.write_text(
        json.dumps(
            {
                "repositories": [],
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
    monkeypatch.setattr(orchestrator_module.time, "sleep", lambda _seconds: None)
    monkeypatch.setattr("tools.web_search.web_search", lambda *args, **kwargs: [])
    monkeypatch.setattr(
        "inference.inference_manager.InferenceManager.get_client",
        staticmethod(lambda provider=None, model=None: DemoLLM()),
    )
    monkeypatch.setattr(api, "API_KEY", "test-key")

    orch = ExegolOrchestrator()
    monkeypatch.setattr(api, "orchestrator", orch)
    client = TestClient(api.app)
    headers = {"X-API-Key": "test-key"}

    registered = client.post(
        "/repos/register",
        json={"repo_path": str(repo_path)},
        headers=headers,
    )
    assert registered.status_code == 200
    assert registered.json()["status"] == "added"

    assert orch.run_fleet_cycle(repo_path=str(repo_path)) is True

    intel = ThrawnIntelManager(str(repo_path)).read_intent()
    assert len(intel["questions"]) >= 4
    queue = HITLManager(str(repo_path)).get_queue()
    assert any(item.get("task") == VADER_BOUNDARY_TASK for item in queue)
    assert any(item.get("category") == "onboarding" and item.get("status") == "pending" for item in queue)

    answers = {
        "primary objective": "Build a browser puzzle game for the AI team demo.",
        "target user": "AI teammates watching a live knowledge-sharing session.",
        "technical constraints": "Use vanilla HTML, CSS, and JavaScript. No paid APIs or external assets.",
        "measure success": "The game runs locally, has a score, has restart, and shows a win or loss state.",
    }
    for question in intel["questions"]:
        question_text = question["question"]
        lowered = question_text.lower()
        answer = next((value for marker, value in answers.items() if marker in lowered), "Keep the live demo small, local, and inspectable.")
        response = client.post(
            "/thrawn/answer",
            json={"repo_path": str(repo_path), "question": question_text, "answer": answer},
            headers=headers,
        )
        assert response.status_code == 200

    vader_task = next(item for item in HITLManager(str(repo_path)).get_queue() if item.get("task") == VADER_BOUNDARY_TASK)
    resolved = client.post(
        "/human-queue/action",
        json={
            "repo_path": str(repo_path),
            "item_id": vader_task["id"],
            "action": "done",
            "notes": "Use a local browser app, no paid APIs, and no placeholder gameplay.",
        },
        headers=headers,
    )
    assert resolved.status_code == 200
    assert not [
        item for item in HITLManager(str(repo_path)).get_pending()
        if item.get("category") == "onboarding"
    ]

    for _ in range(4):
        assert orch.run_fleet_cycle(repo_path=str(repo_path)) is True
        if ObjectiveManager(str(repo_path)).load()["phase"] == "done":
            break

    objective = ObjectiveManager(str(repo_path)).load()
    assert objective["phase"] == "done"
    assert objective["status"] == "done"
    assert objective["last_agent_id"] == "uat_ulic"

    assert (repo_path / "index.html").exists()
    assert (repo_path / "styles.css").exists()
    assert (repo_path / "src" / "game.js").exists()
    assert (repo_path / "README.md").exists()

    active_prompt = (repo_path / ".exegol" / "active_prompt.md").read_text(encoding="utf-8")
    acceptance_report = json.loads((repo_path / ".exegol" / "uat_acceptance_report.json").read_text(encoding="utf-8"))
    game_js = (repo_path / "src" / "game.js").read_text(encoding="utf-8")
    assert acceptance_report["status"] == "pass"
    assert "EXEGOL_ZERO_TO_ONE_GAME" in active_prompt
    assert "Victory" in game_js
    assert "score" in game_js
