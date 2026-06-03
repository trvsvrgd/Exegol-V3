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
from agents.product_poe_agent import ProductPoeAgent
from agents.vibe_vader_agent import VibeVaderAgent
from handoff import HandoffContext, SessionResult
from orchestrator import ExegolOrchestrator
from tools.backlog_manager import BacklogManager
from tools.hitl_manager import HITLManager
from tools.objective_manager import ObjectiveManager
from tools.thrawn_intel_manager import ThrawnIntelManager
from tools.zero_to_one_onboarding import (
    VADER_BOUNDARY_TASK,
    ZERO_TO_ONE_TASK_ID,
    is_zero_to_one_repo,
    vader_onboarding_findings,
)


class PoePlanningClient:
    def generate_system_prompt(self, agent):
        return f"System prompt for {agent.name}"

    def generate(self, *args, **kwargs):
        return '{"salvageable_ids": []}'

    def parse_json_response(self, response):
        return json.loads(response)


@pytest.fixture
def zero_to_one_orchestrator(tmp_path, monkeypatch):
    repo_path = tmp_path / "fresh_repo"
    repo_path.mkdir()
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

    return ExegolOrchestrator(), repo_path


def test_zero_to_one_detection_treats_readme_as_low_signal(tmp_path):
    repo_path = tmp_path / "repo"
    repo_path.mkdir()
    (repo_path / "README.md").write_text("# Demo\n", encoding="utf-8")

    assert is_zero_to_one_repo(str(repo_path)) is True

    (repo_path / "src").mkdir()
    (repo_path / "src" / "main.py").write_text("print('hello')\n", encoding="utf-8")

    assert is_zero_to_one_repo(str(repo_path)) is False


def test_empty_repo_without_exegol_dispatches_thrawn(zero_to_one_orchestrator, monkeypatch):
    orch, repo_path = zero_to_one_orchestrator
    calls = []

    monkeypatch.setattr(
        orch,
        "wake_and_execute_agent",
        lambda repo_info, routing, max_steps, agent_id=None, **kwargs: calls.append(agent_id),
    )

    orch.process_repo(orch._repo_info_for_path(str(repo_path)))

    assert calls == ["thoughtful_thrawn", "vibe_vader"]
    state = json.loads((repo_path / ".exegol" / "fleet_state.json").read_text(encoding="utf-8"))
    assert state["status"] == "awaiting_human"
    assert "onboarding" in state["status_detail"].lower()


def test_targeted_empty_repo_defers_scheduled_jobs_until_onboarding(zero_to_one_orchestrator, monkeypatch):
    orch, repo_path = zero_to_one_orchestrator
    calls = []
    due_calls = []

    monkeypatch.setattr(
        orch,
        "run_due_scheduled_agents",
        lambda **kwargs: due_calls.append(kwargs) or {"triggered_count": 1},
    )
    monkeypatch.setattr(orch, "check_compliance_monitoring", lambda: None)
    monkeypatch.setattr(
        orch,
        "wake_and_execute_agent",
        lambda repo_info, routing, max_steps, agent_id=None, **kwargs: calls.append(agent_id),
    )

    assert orch.run_fleet_cycle(
        repo_path=str(repo_path),
        include_due_scheduled=True,
        trigger_source="manual_run",
    ) is True

    assert due_calls == []
    assert calls == ["thoughtful_thrawn", "vibe_vader"]


def test_targeted_zero_to_one_objective_defers_scheduled_jobs_until_content_exists(
    zero_to_one_orchestrator,
    monkeypatch,
):
    orch, repo_path = zero_to_one_orchestrator
    (repo_path / ".exegol").mkdir()
    ObjectiveManager(str(repo_path)).create_or_update(
        goal="Build a browser puzzle game for the AI team demo.",
        success_criteria=["Playable locally."],
        constraints=["Vanilla HTML, CSS, and JavaScript."],
    )
    due_calls = []
    processed = []

    monkeypatch.setattr(
        orch,
        "run_due_scheduled_agents",
        lambda **kwargs: due_calls.append(kwargs) or {"triggered_count": 1},
    )
    monkeypatch.setattr(orch, "check_compliance_monitoring", lambda: None)
    monkeypatch.setattr(orch, "process_repo", lambda repo_info: processed.append(repo_info))

    assert orch.run_fleet_cycle(
        repo_path=str(repo_path),
        include_due_scheduled=True,
        trigger_source="manual_run",
    ) is True

    assert due_calls == []
    assert processed[0]["repo_path"] == os.path.abspath(str(repo_path))


def test_targeted_running_objective_defers_scheduled_jobs_after_content_exists(
    zero_to_one_orchestrator,
    monkeypatch,
):
    orch, repo_path = zero_to_one_orchestrator
    (repo_path / ".exegol").mkdir()
    (repo_path / "index.html").write_text("<!doctype html>\n", encoding="utf-8")
    manager = ObjectiveManager(str(repo_path))
    manager.create_or_update(
        goal="Build a browser puzzle game for the AI team demo.",
        success_criteria=["Playable locally."],
        constraints=["Vanilla HTML, CSS, and JavaScript."],
    )
    manager.transition("planning")
    due_calls = []
    processed = []

    monkeypatch.setattr(
        orch,
        "run_due_scheduled_agents",
        lambda **kwargs: due_calls.append(kwargs) or {"triggered_count": 1},
    )
    monkeypatch.setattr(orch, "check_compliance_monitoring", lambda: None)
    monkeypatch.setattr(orch, "process_repo", lambda repo_info: processed.append(repo_info))

    assert orch.run_fleet_cycle(
        repo_path=str(repo_path),
        include_due_scheduled=True,
        trigger_source="manual_run",
    ) is True

    assert due_calls == []
    assert processed[0]["repo_path"] == os.path.abspath(str(repo_path))


def test_empty_repo_waits_for_onboarding_answers(zero_to_one_orchestrator, monkeypatch):
    orch, repo_path = zero_to_one_orchestrator
    exegol_dir = repo_path / ".exegol"
    exegol_dir.mkdir()
    question = "What is the Primary Objective of this repository? (Elevator pitch)"
    ThrawnIntelManager(str(repo_path)).save_intent({
        "objective": "",
        "architecture": [],
        "questions": [{"question": question, "answer": None}],
    })
    HITLManager(str(repo_path)).add_task(
        task=f"Thrawn: {question[:60]}...",
        context="Thoughtful Thrawn requires project clarity.",
        category="onboarding",
        task_id="thrawn_primary",
    )

    monkeypatch.setattr(
        orch,
        "wake_and_execute_agent",
        lambda *args, **kwargs: pytest.fail("onboarding should block autonomous coding"),
    )

    orch.process_repo(orch._repo_info_for_path(str(repo_path)))

    state = json.loads((exegol_dir / "fleet_state.json").read_text(encoding="utf-8"))
    assert state["status"] == "awaiting_human"
    assert state["active_agent"] == "thoughtful_thrawn"
    assert "Waiting for human onboarding input" in state["output_summary"]


def test_primary_intent_allows_build_while_secondary_onboarding_is_pending(
    zero_to_one_orchestrator,
    monkeypatch,
):
    orch, repo_path = zero_to_one_orchestrator
    (repo_path / ".exegol").mkdir()
    ThrawnIntelManager(str(repo_path)).save_intent({
        "objective": "",
        "architecture": [],
        "questions": [
            {
                "question": "What is the Primary Objective of this repository? (Elevator pitch)",
                "answer": "Build a browser puzzle game for the AI team demo.",
            },
            {
                "question": "Who is the target user for this project?",
                "answer": None,
            },
        ],
    })
    HITLManager(str(repo_path)).add_task(
        task=VADER_BOUNDARY_TASK,
        context="Capture demo boundaries.",
        category="onboarding",
        task_id="vader_boundaries",
    )
    calls = []

    def fake_wake(repo_info, routing, max_steps, agent_id=None, **kwargs):
        calls.append(agent_id)
        return SessionResult(
            agent_id=agent_id or "unknown",
            session_id="sess_zero_to_one",
            outcome="success",
            output_summary="planned",
        )

    monkeypatch.setattr(orch, "wake_and_execute_agent", fake_wake)

    orch.process_repo(orch._repo_info_for_path(str(repo_path)))

    objective = ObjectiveManager(str(repo_path)).load()
    state = json.loads((repo_path / ".exegol" / "fleet_state.json").read_text(encoding="utf-8"))
    assert calls == ["product_poe"]
    assert objective["goal"] == "Build a browser puzzle game for the AI team demo."
    assert state["status"] != "awaiting_human"


def test_resolved_onboarding_seeds_objective_and_dispatches_product_poe(zero_to_one_orchestrator, monkeypatch):
    orch, repo_path = zero_to_one_orchestrator
    (repo_path / ".exegol").mkdir()
    ThrawnIntelManager(str(repo_path)).save_intent({
        "objective": "",
        "architecture": [],
        "questions": [
            {
                "question": "What is the Primary Objective of this repository? (Elevator pitch)",
                "answer": "Build a browser puzzle game for the AI team demo.",
            },
            {
                "question": "Who is the target user for this project?",
                "answer": "AI teammates watching a live knowledge-sharing session.",
            },
            {
                "question": "How will we measure success for this project?",
                "answer": "The game runs locally and shows a complete playable loop.",
            },
        ],
    })
    hitl = HITLManager(str(repo_path))
    hitl.add_task(
        task=VADER_BOUNDARY_TASK,
        context="Capture demo boundaries.",
        category="onboarding",
        task_id="vader_boundaries",
    )
    hitl.resolve_task(
        item_id="vader_boundaries",
        status="done",
        notes="Use a local browser app, no paid APIs, and avoid placeholder gameplay.",
    )
    calls = []

    def fake_wake(repo_info, routing, max_steps, agent_id=None, **kwargs):
        calls.append(agent_id)
        return SessionResult(
            agent_id=agent_id or "unknown",
            session_id="sess_zero_to_one",
            outcome="success",
            output_summary="planned",
        )

    monkeypatch.setattr(orch, "wake_and_execute_agent", fake_wake)

    orch.process_repo(orch._repo_info_for_path(str(repo_path)))

    objective = ObjectiveManager(str(repo_path)).load()
    task = BacklogManager(str(repo_path)).get_task(ZERO_TO_ONE_TASK_ID)
    assert calls == ["product_poe"]
    assert objective["goal"] == "Build a browser puzzle game for the AI team demo."
    assert objective["phase"] == "implementing"
    assert objective["success_criteria"] == []
    assert "no paid APIs" in " ".join(objective["constraints"])
    assert task is None


def test_product_poe_defines_zero_to_one_requirements_roadmap_and_build_task(tmp_path):
    repo_path = tmp_path / "repo"
    repo_path.mkdir()
    (repo_path / ".exegol").mkdir()
    ThrawnIntelManager(str(repo_path)).save_intent({
        "objective": "",
        "architecture": [],
        "questions": [
            {
                "question": "What is the Primary Objective of this repository? (Elevator pitch)",
                "answer": "Build a browser puzzle game for the AI team demo.",
            },
            {
                "question": "Who is the target user for this project?",
                "answer": "AI teammates watching a live knowledge-sharing session.",
            },
            {
                "question": "What technical constraints should guide the build?",
                "answer": "Use vanilla HTML, CSS, and JavaScript with no paid APIs.",
            },
            {
                "question": "How will we measure success for this project?",
                "answer": "The game runs locally, tracks score, and shows win or loss feedback.",
            },
        ],
    })
    manager = ObjectiveManager(str(repo_path))
    manager.create_or_update(
        goal="Build a browser puzzle game for the AI team demo.",
        constraints=["Use vanilla HTML, CSS, and JavaScript with no paid APIs."],
    )
    manager.transition("planning", last_agent_id="orchestrator")

    agent = ProductPoeAgent(PoePlanningClient())
    result = agent.execute(HandoffContext(
        repo_path=str(repo_path),
        agent_id="product_poe",
        task_id="fleet_cycle",
        model_routing="ollama",
        max_steps=10,
    ))

    objective = ObjectiveManager(str(repo_path)).load()
    task = BacklogManager(str(repo_path)).get_task(ZERO_TO_ONE_TASK_ID)
    roadmap = ThrawnIntelManager(str(repo_path)).read_roadmap()
    roadmap_brief = json.loads((repo_path / ".exegol" / "roadmap_brief.json").read_text(encoding="utf-8"))
    active_prompt = (repo_path / ".exegol" / "active_prompt.md").read_text(encoding="utf-8")
    criteria_text = " ".join(objective["success_criteria"]).lower()

    assert "Active task set: zero_to_one_build" in result
    assert "playable loop" in criteria_text
    assert "win or loss feedback" in criteria_text
    assert "Poe-Defined Success Requirements" in roadmap
    assert "Post-MVP Roadmap" in roadmap
    assert task["source_agent"] == "product_poe"
    assert task["target_agent"] == "developer_dex"
    assert task["status"] == "in_progress"
    assert task["acceptance_criteria"] == objective["success_criteria"]
    assert task["post_mvp_roadmap"]
    assert roadmap_brief["owner_agent"] == "product_poe"
    assert roadmap_brief["freshness"] == "poe_refreshed"
    assert roadmap_brief["mvp"]["success_criteria"] == objective["success_criteria"][:4]
    assert roadmap_brief["long_term"]
    assert "EXEGOL_ZERO_TO_ONE_GAME" in active_prompt
    assert agent.next_agent_id == "developer_dex"


def test_vader_onboarding_prompt_is_one_time_for_empty_repos(tmp_path):
    repo_path = tmp_path / "repo"
    repo_path.mkdir()

    findings = vader_onboarding_findings(str(repo_path))

    assert findings == [
        {
            "task": VADER_BOUNDARY_TASK,
            "category": "onboarding",
            "context": (
                "Before autonomous coding begins, state the build boundaries: game genre, "
                "allowed stack, asset/network limits, unacceptable shortcuts, and what must "
                "be visible in the live demo."
            ),
        }
    ]

    HITLManager(str(repo_path)).add_task(
        task=VADER_BOUNDARY_TASK,
        context="already asked",
        category="onboarding",
        task_id="vader_boundaries",
    )

    assert vader_onboarding_findings(str(repo_path)) == []


def test_vader_zero_to_one_onboarding_skips_readiness_noise(tmp_path, monkeypatch):
    repo_path = tmp_path / "repo"
    (repo_path / ".git").mkdir(parents=True)

    monkeypatch.setattr(
        "agents.vibe_vader_agent.web_search",
        lambda *args, **kwargs: pytest.fail("zero-to-one onboarding should not run market search"),
    )
    monkeypatch.setattr(
        "agents.vibe_vader_agent.analyze_repository",
        lambda *args, **kwargs: pytest.fail("zero-to-one onboarding should not run repo audit"),
    )

    handoff = HandoffContext(
        repo_path=str(repo_path),
        agent_id="vibe_vader",
        task_id="fleet_cycle",
        model_routing="ollama",
        max_steps=10,
    )

    result = VibeVaderAgent(llm_client=None).execute(handoff)

    queue = HITLManager(str(repo_path)).get_queue()
    assert "Report generated with 1 items" in result
    assert len(queue) == 1
    assert queue[0]["task"] == VADER_BOUNDARY_TASK
    assert queue[0]["category"] == "onboarding"
