import os
import sys

os.environ["EXEGOL_DISABLE_SCHEDULER"] = "true"
os.environ["EXEGOL_DISABLE_SLACK"] = "true"
os.environ["SLACK_BOT_TOKEN"] = ""
os.environ["SLACK_APP_TOKEN"] = ""
os.environ["SLACK_WEBHOOK_URL"] = ""

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

import api
from fastapi.testclient import TestClient


def test_supervisor_health_endpoint_shape(monkeypatch):
    monkeypatch.setattr(
        api,
        "build_supervisor_health",
        lambda _orchestrator, _status, **_kwargs: {
            "status": "ok",
            "checked_at": "2026-05-19T00:00:00",
            "services": {"backend": {"status": "ok", "detail": "Backend process is responding."}},
            "repositories": [],
            "degraded_services": [],
            "degraded_repositories": [],
        },
    )
    client = TestClient(api.app)
    api_key = os.getenv("EXEGOL_API_KEY", "dev-local-key")

    response = client.get("/fleet/supervisor-health", headers={"X-API-Key": api_key})

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert "services" in data
    assert "repositories" in data
