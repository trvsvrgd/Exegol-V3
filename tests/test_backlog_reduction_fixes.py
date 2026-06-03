import datetime
from types import SimpleNamespace

from agents.compliance_cody_agent import ComplianceCodyAgent
from agents.evaluator_ezra_agent import EvaluatorEzraAgent
from agents.uat_ulic_agent import UatUlicAgent
from tools.backlog_manager import BacklogManager
from tools.model_benchmark_db import recommend_for_role, upsert_model
from tools.objective_manager import ObjectiveManager


class StaticJsonClient:
    def __init__(self, parsed):
        self.parsed = parsed

    def generate_system_prompt(self, _agent):
        return "system"

    def generate(self, *args, **kwargs):
        return "response"

    def parse_json_response(self, _response):
        return self.parsed


def test_evaluator_stale_requirement_output_is_cp1252_safe(tmp_path, monkeypatch, capsys):
    old_date = (datetime.datetime.now() - datetime.timedelta(days=45)).isoformat()
    EvaluatorEzraAgent._save_eval_requirements(
        str(tmp_path),
        [{
            "id": "eval_req_stale",
            "technique_name": "Old evaluation",
            "status": "pending",
            "added_date": old_date,
        }],
    )
    agent = EvaluatorEzraAgent(StaticJsonClient([]))
    monkeypatch.setattr(agent, "_research_latest_techniques", lambda: [])

    from tools.llm_judge import LLMJudge
    monkeypatch.setattr(LLMJudge, "audit_agent", lambda *_args, **_kwargs: {"error": "skip live judge"})

    result = agent.execute(SimpleNamespace(repo_path=str(tmp_path), session_id="ezra-test"))

    output = capsys.readouterr().out
    output.encode("cp1252")
    assert "WARNING:" in output
    assert "stale flagged" in result


def test_compliance_cody_ignores_malformed_llm_requirements(tmp_path, monkeypatch):
    from agents import compliance_cody_agent

    monkeypatch.setattr(compliance_cody_agent, "web_search", lambda *_args, **_kwargs: [])
    agent = ComplianceCodyAgent(StaticJsonClient("not a requirement list"))

    result = agent.execute(SimpleNamespace(repo_path=str(tmp_path), session_id="cody-test"))

    assert "Compliance sweep complete" in result
    assert BacklogManager(str(tmp_path)).load_backlog() == []


def test_model_recommendations_tolerate_nullable_scores(tmp_path):
    upsert_model(str(tmp_path), {
        "model_name": "Null Score Model",
        "provider": "TestProvider",
        "coding_score": None,
        "agentic_score": None,
        "reasoning_score": None,
        "speed_score": None,
        "cost_score": None,
    })

    recommendations = recommend_for_role(str(tmp_path), "coding")

    assert recommendations
    assert all(isinstance(item["weighted_score"], float) for item in recommendations)


def test_uat_does_not_create_placeholder_ui_bug_backlog_items(tmp_path):
    agent = UatUlicAgent(StaticJsonClient({}))

    result = agent.execute(SimpleNamespace(repo_path=str(tmp_path), session_id="uat-test"))

    assert "No actionable UI anomalies detected" in result
    assert BacklogManager(str(tmp_path)).load_backlog() == []
    assert agent.success_metrics["ui_bugs_detected"]["current"] == "0"


def test_uat_accepts_zero_to_one_game_when_poe_criteria_are_met(tmp_path):
    (tmp_path / "src").mkdir()
    (tmp_path / "index.html").write_text("<button>Start</button><script src='src/game.js'></script>", encoding="utf-8")
    (tmp_path / "styles.css").write_text("body { color: white; }", encoding="utf-8")
    (tmp_path / "src" / "game.js").write_text(
        "let score = 0; function restart(){} const message = 'Victory or final score';",
        encoding="utf-8",
    )
    (tmp_path / "README.md").write_text("## Run\nOpen `index.html` in a browser for the demo game.\n", encoding="utf-8")
    ObjectiveManager(str(tmp_path)).create_or_update(
        goal="Build a browser puzzle game for the AI team demo.",
        success_criteria=[
            "The repository contains a runnable application aligned with the stated objective.",
            "The app has enough polish and instructions to demo live from a fresh checkout.",
            "The game has a playable loop, clear controls, and visible win/lose or scoring feedback.",
        ],
    )
    agent = UatUlicAgent(StaticJsonClient({}))

    result = agent.execute(SimpleNamespace(repo_path=str(tmp_path), session_id="uat-pass"))

    report = (tmp_path / ".exegol" / "uat_acceptance_report.json").read_text(encoding="utf-8")
    assert "Objective Acceptance: pass" in result
    assert agent.outcome == "success"
    assert '"status": "pass"' in report
    assert not [task for task in BacklogManager(str(tmp_path)).load_backlog() if task["id"].startswith("uat_acceptance_fix_")]


def test_uat_rejects_zero_to_one_game_when_poe_criteria_are_missing(tmp_path):
    (tmp_path / "README.md").write_text("## Run\nOpen the demo.\n", encoding="utf-8")
    ObjectiveManager(str(tmp_path)).create_or_update(
        goal="Build a browser puzzle game for the AI team demo.",
        success_criteria=[
            "The repository contains a runnable application aligned with the stated objective.",
            "The game has a playable loop, clear controls, and visible win/lose or scoring feedback.",
        ],
    )
    agent = UatUlicAgent(StaticJsonClient({}))

    result = agent.execute(SimpleNamespace(repo_path=str(tmp_path), session_id="uat-fail"))

    tasks = BacklogManager(str(tmp_path)).load_backlog()
    assert "Objective Acceptance: fail" in result
    assert agent.outcome == "failure"
    assert agent.errors
    assert any(task["id"].startswith("uat_acceptance_fix_") and task["target_agent"] == "developer_dex" for task in tasks)
