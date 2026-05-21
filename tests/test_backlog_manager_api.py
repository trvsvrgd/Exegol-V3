import os

from fastapi.testclient import TestClient

import api


def test_backlog_api_uses_manager_for_add_update_and_reorder(tmp_path):
    client = TestClient(api.app)
    headers = {"X-API-Key": os.getenv("EXEGOL_API_KEY", "dev-local-key")}

    first = client.post(
        "/backlog/add",
        json={"repo_path": str(tmp_path), "summary": "First task", "priority": "high"},
        headers=headers,
    )
    second = client.post(
        "/backlog/add",
        json={"repo_path": str(tmp_path), "summary": "Second task", "priority": "medium"},
        headers=headers,
    )

    assert first.status_code == 200
    assert second.status_code == 200
    first_id = first.json()["task"]["id"]
    second_id = second.json()["task"]["id"]

    update = client.post(
        "/backlog/update",
        json={"repo_path": str(tmp_path), "task_id": first_id, "updates": {"status": "done"}},
        headers=headers,
    )
    assert update.status_code == 200

    reorder = client.post(
        "/backlog/reorder",
        json={"repo_path": str(tmp_path), "task_ids": [second_id, first_id]},
        headers=headers,
    )
    assert reorder.status_code == 200

    backlog = client.get(f"/backlog?repo_path={tmp_path}", headers=headers).json()
    assert [task["id"] for task in backlog] == [second_id, first_id]
    ranked = {task["id"]: task.get("rank") for task in backlog}
    assert ranked[second_id] == 0
    assert ranked[first_id] == 1
    assert next(task for task in backlog if task["id"] == first_id)["status"] == "done"
