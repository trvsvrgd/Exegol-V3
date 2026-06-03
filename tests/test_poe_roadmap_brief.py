import json
import os
import sys

from fastapi.testclient import TestClient


os.environ["EXEGOL_DISABLE_SCHEDULER"] = "true"
os.environ["EXEGOL_DISABLE_SLACK"] = "true"
os.environ["SLACK_BOT_TOKEN"] = ""
os.environ["SLACK_APP_TOKEN"] = ""
os.environ["SLACK_WEBHOOK_URL"] = ""

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

import api
from tools.poe_roadmap_brief import build_poe_roadmap_brief, load_or_build_poe_roadmap_brief


def _headers():
    return {"X-API-Key": os.getenv("EXEGOL_API_KEY", "dev-local-key")}


def _write_json(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data), encoding="utf-8")


def test_roadmap_brief_caps_sections_and_uses_verified_accomplishments(tmp_path):
    exegol = tmp_path / ".exegol"
    exegol.mkdir()
    _write_json(
        exegol / "objective.json",
        {
            "id": "objective_123",
            "goal": "Make the autonomous loop understandable.",
            "phase": "implementing",
            "status": "running",
            "loop_count": 3,
            "active_task_id": "task_active",
            "success_criteria": [
                "Shows current objective.",
                "Shows current phase.",
                "Shows active agent.",
                "Shows next action.",
                "Shows blocker reason.",
            ],
            "constraints": ["No live LLM interpretation.", "Readable in one minute."],
        },
    )
    (exegol / "roadmap.md").write_text(
        "\n".join(
            [
                "# Roadmap",
                "",
                "## MVP",
                "Make the autonomous loop understandable.",
                "",
                "## Poe-Defined Success Requirements",
                "- Shows current focus.",
                "",
                "## Human Constraints",
                "- Keep it compact.",
                "",
                "## Post-MVP Roadmap",
                "- Add objective event drilldown.",
                "- Add validation trend summaries.",
                "- Add cost anomaly signals.",
                "- Add Slack handoff summaries.",
                "- Add weekly roadmap digest.",
                "",
                "- [x] Poe defined MVP success criteria.",
                "- [ ] This unchecked item must not be counted as done.",
            ]
        ),
        encoding="utf-8",
    )
    (tmp_path / "ROADMAP.md").write_text(
        "\n".join(
            [
                "# Root Roadmap",
                "- [x] Start the Workbench frontend in production mode.",
                "",
                "## Priority 1: Safety For Autonomous Work",
                "- [ ] Add cost ceilings.",
            ]
        ),
        encoding="utf-8",
    )
    _write_json(
        exegol / "backlog.json",
        [{"id": "task_active", "summary": "Build the Poe roadmap brief", "status": "in_progress"}],
    )
    _write_json(
        exegol / "backlog_archive.json",
        [
            {"id": "done_1", "summary": "Implemented objective event capture", "status": "completed"},
            {"id": "done_2", "summary": "Archived stale blockers", "status": "done"},
        ],
    )

    brief = build_poe_roadmap_brief(str(tmp_path))

    assert brief["current_focus"] == "Working on: Build the Poe roadmap brief"
    assert len(brief["accomplished"]) == 3
    assert {item["evidence"] for item in brief["accomplished"]} == {"roadmap", "completed_task"}
    assert "unchecked" not in " ".join(item["text"].lower() for item in brief["accomplished"])
    assert brief["mvp"]["success_criteria"] == [
        "Shows current objective.",
        "Shows current phase.",
        "Shows active agent.",
        "Shows next action.",
    ]
    assert brief["mvp"]["constraints"] == ["No live LLM interpretation.", "Readable in one minute.", "Keep it compact."]
    assert len(brief["long_term"]) == 4
    assert brief["long_term"][0]["text"] == "Add objective event drilldown."


def test_roadmap_brief_marks_blocked_objective(tmp_path):
    exegol = tmp_path / ".exegol"
    exegol.mkdir()
    _write_json(
        exegol / "objective.json",
        {
            "id": "objective_blocked",
            "goal": "Ship the roadmap view.",
            "phase": "blocked_human",
            "status": "blocked",
            "blocked_reason": "Need MVP scope decision.",
        },
    )

    brief = build_poe_roadmap_brief(str(tmp_path))

    assert brief["mvp"]["status"] == "blocked"
    assert brief["current_focus"] == "Blocked: Need MVP scope decision."
    assert brief["objective"]["blocked_reason"] == "Need MVP scope decision."


def test_roadmap_brief_missing_state_is_empty_fallback(tmp_path):
    brief = load_or_build_poe_roadmap_brief(str(tmp_path))

    assert brief["freshness"] == "computed_fallback"
    assert brief["mvp"]["status"] == "not_defined"
    assert brief["current_focus"] == "No roadmap objective captured yet."
    assert brief["accomplished"] == []


def test_poe_roadmap_api_returns_normal_brief(tmp_path):
    exegol = tmp_path / ".exegol"
    exegol.mkdir()
    _write_json(
        exegol / "objective.json",
        {
            "goal": "Make roadmap state visible.",
            "phase": "planning",
            "status": "running",
            "success_criteria": ["Roadmap endpoint returns structured data."],
        },
    )
    client = TestClient(api.app)

    response = client.get("/poe/roadmap", params={"repo_path": str(tmp_path)}, headers=_headers())

    assert response.status_code == 200
    data = response.json()
    assert data["owner_agent"] == "product_poe"
    assert data["objective"]["goal"] == "Make roadmap state visible."
    assert data["mvp"]["status"] == "planning"


def test_poe_roadmap_api_returns_missing_state_fallback(tmp_path):
    client = TestClient(api.app)

    response = client.get("/poe/roadmap", params={"repo_path": str(tmp_path)}, headers=_headers())

    assert response.status_code == 200
    data = response.json()
    assert data["freshness"] == "computed_fallback"
    assert data["mvp"]["status"] == "not_defined"
