import json
import os

from fastapi.testclient import TestClient

os.environ["SLACK_BOT_TOKEN"] = ""
os.environ["SLACK_APP_TOKEN"] = ""
os.environ["SLACK_WEBHOOK_URL"] = ""
os.environ["EXEGOL_DISABLE_SCHEDULER"] = "true"

import api


def _headers():
    return {"X-API-Key": os.getenv("EXEGOL_API_KEY", "dev-local-key")}


def _write_interaction_log(
    repo_path,
    filename,
    timestamp,
    agent_id,
    outcome="success",
    session_id=None,
    errors=None,
):
    logs_dir = repo_path / ".exegol" / "interaction_logs"
    logs_dir.mkdir(parents=True, exist_ok=True)
    payload = {
        "timestamp": timestamp,
        "agent_id": agent_id,
        "session_id": session_id or filename.removesuffix(".json"),
        "outcome": outcome,
        "task_summary": f"{agent_id} {outcome}",
        "steps_used": 1,
        "duration_seconds": 1.0,
        "errors": errors or [],
        "state_changes": {},
        "metrics": {},
        "token_usage": 0,
        "prompt_count": 0,
        "repo_path": str(repo_path),
    }
    (logs_dir / filename).write_text(json.dumps(payload), encoding="utf-8")


def test_fleet_metrics_defaults_to_may_31_baseline(tmp_path):
    _write_interaction_log(
        tmp_path,
        "old_failure.json",
        "2026-05-30T23:59:59",
        "WatcherWedgeAgent",
        outcome="failure",
        session_id="old-failure",
        errors=["stale failure"],
    )
    _write_interaction_log(
        tmp_path,
        "new_success.json",
        "2026-05-31T00:00:00",
        "WatcherWedgeAgent",
        outcome="success",
        session_id="new-success",
    )

    client = TestClient(api.app)
    response = client.get(
        "/fleet/metrics",
        params={"repo_path": str(tmp_path)},
        headers=_headers(),
    )

    assert response.status_code == 200
    data = response.json()
    watcher = data["agent_breakdown"]["watcher_wedge"]
    assert data["period_start"].startswith("2026-05-31T00:00:00")
    assert data["period_label"] == "Since 2026-05-31"
    assert data["fleet_aggregate"]["total_sessions"] == 1
    assert watcher["total_sessions"] == 1
    assert watcher["bugs_introduced"] == 0
    assert watcher["recall"] == 1.0


def test_interactions_start_date_filters_and_normalizes_agent_ids(tmp_path):
    _write_interaction_log(
        tmp_path,
        "old_watcher.json",
        "2026-05-30T23:59:59",
        "WatcherWedgeAgent",
        session_id="old-watcher",
    )
    _write_interaction_log(
        tmp_path,
        "class_watcher.json",
        "2026-05-31T00:00:00",
        "WatcherWedgeAgent",
        session_id="class-watcher",
    )
    _write_interaction_log(
        tmp_path,
        "snake_watcher.json",
        "2026-05-31T00:00:01",
        "watcher_wedge",
        session_id="snake-watcher",
    )

    client = TestClient(api.app)
    response = client.get(
        "/fleet/interactions",
        params={
            "repo_path": str(tmp_path),
            "start_date": "2026-05-31",
            "agent_id": "watcher_wedge",
        },
        headers=_headers(),
    )

    assert response.status_code == 200
    logs = response.json()
    assert {log["session_id"] for log in logs} == {"class-watcher", "snake-watcher"}
    assert {log["agent_id"] for log in logs} == {"WatcherWedgeAgent", "watcher_wedge"}
