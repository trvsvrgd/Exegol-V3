import json
import os
import sys

from fastapi.testclient import TestClient

os.environ["SLACK_BOT_TOKEN"] = ""
os.environ["SLACK_APP_TOKEN"] = ""
os.environ["SLACK_WEBHOOK_URL"] = ""
os.environ["EXEGOL_DISABLE_SCHEDULER"] = "true"

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

import api


def _headers():
    return {"X-API-Key": os.getenv("EXEGOL_API_KEY", "dev-local-key")}


def test_operations_endpoint_matches_dashboard_contract(monkeypatch, tmp_path):
    exegol_dir = tmp_path / ".exegol"
    exegol_dir.mkdir()
    (exegol_dir / "backlog.json").write_text(
        json.dumps([{"id": "task_1", "status": "todo"}]),
        encoding="utf-8",
    )
    (exegol_dir / "user_action_required.json").write_text(
        json.dumps(
            [
                {
                    "id": "blocker_agent_crash_backend",
                    "task": "SUPERVISOR BLOCKER: backend dead",
                    "category": "blocker",
                    "blocker_type": "agent_crash",
                    "status": "pending",
                }
            ]
        ),
        encoding="utf-8",
    )
    (exegol_dir / "supervisor_state.json").write_text(
        json.dumps(
            {
                "status": "degraded",
                "components": {
                    "docker": {"status": "healthy"},
                    "frontend": {"status": "healthy"},
                },
            }
        ),
        encoding="utf-8",
    )

    monkeypatch.setattr(api, "read_interaction_logs", lambda *_args, **_kwargs: [])
    client = TestClient(api.app)

    response = client.get(
        "/fleet/operations",
        params={"repo_path": str(tmp_path)},
        headers=_headers(),
    )

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "degraded"
    assert data["components"]["docker"]["status"] == "healthy"
    assert data["latest_blocker"]["id"] == "blocker_agent_crash_backend"
    assert data["latest_blocker_type"] == "agent_crash"
    assert data["queue_length"] == 1
    assert "health_report" in data


def test_clear_blocker_resolves_queue_item(tmp_path):
    exegol_dir = tmp_path / ".exegol"
    exegol_dir.mkdir()
    queue_path = exegol_dir / "user_action_required.json"
    queue_path.write_text(
        json.dumps(
            [
                {
                    "id": "blocker_agent_crash_backend",
                    "task": "SUPERVISOR BLOCKER: backend dead",
                    "category": "blocker",
                    "blocker_type": "agent_crash",
                    "status": "pending",
                }
            ]
        ),
        encoding="utf-8",
    )
    client = TestClient(api.app)

    response = client.post(
        "/blockers/clear",
        json={"repo_path": str(tmp_path), "blocker_id": "blocker_agent_crash_backend"},
        headers=_headers(),
    )

    assert response.status_code == 200
    queue = json.loads(queue_path.read_text(encoding="utf-8"))
    assert queue[0]["status"] == "done"


def test_retry_go_rejects_manual_hitl_blocker(tmp_path):
    exegol_dir = tmp_path / ".exegol"
    exegol_dir.mkdir()
    (exegol_dir / "user_action_required.json").write_text(
        json.dumps(
            [
                {
                    "id": "manual_blocker",
                    "task": "Need user decision",
                    "category": "blocker",
                    "blocker_type": "manual_hitl",
                    "status": "pending",
                }
            ]
        ),
        encoding="utf-8",
    )
    client = TestClient(api.app)

    response = client.post(
        "/blockers/retry-go",
        json={"repo_path": str(tmp_path), "blocker_id": "manual_blocker"},
        headers=_headers(),
    )

    assert response.status_code == 409
