import os
import sys

os.environ["EXEGOL_DISABLE_SCHEDULER"] = "true"
os.environ["EXEGOL_DISABLE_SLACK"] = "true"
os.environ["SLACK_BOT_TOKEN"] = ""
os.environ["SLACK_APP_TOKEN"] = ""
os.environ["SLACK_WEBHOOK_URL"] = ""

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from api import BacklogUpdateRequest, add_to_backlog, get_backlog, reorder_backlog, update_backlog


def test_backlog_api_uses_manager_and_syncs_json(tmp_path):
    repo_path = str(tmp_path / "repo")

    added = add_to_backlog({
        "repo_path": repo_path,
        "summary": "Harden supervisor health loop",
        "priority": "high",
    })

    task_id = added["task"]["id"]
    tasks = get_backlog(repo_path)
    assert any(task["id"] == task_id for task in tasks)

    update_backlog(BacklogUpdateRequest(
        repo_path=repo_path,
        task_id=task_id,
        updates={"status": "in_progress", "owner": "developer_dex"},
    ))

    updated = get_backlog(repo_path)
    task = next(task for task in updated if task["id"] == task_id)
    assert task["status"] == "in_progress"
    assert task["owner"] == "developer_dex"


def test_backlog_reorder_uses_manager_rank(tmp_path):
    repo_path = str(tmp_path / "repo")
    first = add_to_backlog({"repo_path": repo_path, "summary": "First task"})["task"]["id"]
    second = add_to_backlog({"repo_path": repo_path, "summary": "Second task"})["task"]["id"]

    reorder_backlog({"repo_path": repo_path, "task_ids": [second, first]})

    tasks = get_backlog(repo_path)
    assert [task["id"] for task in tasks[:2]] == [second, first]
    assert tasks[0]["rank"] == 0
    assert tasks[1]["rank"] == 1
