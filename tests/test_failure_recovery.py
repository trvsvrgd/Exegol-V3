import hashlib
import hmac
import json
import os
import sys

os.environ["EXEGOL_DISABLE_SLACK"] = "true"
os.environ["SLACK_BOT_TOKEN"] = ""
os.environ["SLACK_APP_TOKEN"] = ""
os.environ["SLACK_WEBHOOK_URL"] = ""

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from handoff import HandoffContext
from session_manager import SessionManager
from tools.backlog_manager import BacklogManager
from tools.fleet_logger import failure_backlog_task_id, log_interaction


def _signed_handoff(repo_path, agent_id="developer_dex", session_id="sess_failure"):
    handoff = HandoffContext(
        repo_path=str(repo_path),
        agent_id=agent_id,
        task_id="task_1",
        model_routing="ollama",
        max_steps=3,
        session_id=session_id,
    )
    secret = os.getenv("EXEGOL_HMAC_SECRET", "dev-secret-keep-it-safe")
    data = f"{handoff.repo_path}|{handoff.agent_id}|{handoff.session_id}|{handoff.timestamp}"
    signature = hmac.new(secret.encode(), data.encode(), hashlib.sha256).hexdigest()
    return HandoffContext(
        repo_path=handoff.repo_path,
        agent_id=handoff.agent_id,
        task_id=handoff.task_id,
        model_routing=handoff.model_routing,
        max_steps=handoff.max_steps,
        session_id=handoff.session_id,
        timestamp=handoff.timestamp,
        signature=signature,
    )


def test_failure_log_updates_one_backlog_blocker(tmp_path):
    repo_path = tmp_path / "repo"
    repo_path.mkdir()
    errors = ["RuntimeError: boom"]
    summary = "Agent execution failed: RuntimeError: boom"
    expected_id = failure_backlog_task_id("developer_dex", summary, errors)

    first_log = log_interaction(
        agent_id="developer_dex",
        outcome="failure",
        task_summary=summary,
        repo_path=str(repo_path),
        errors=errors,
        session_id="first",
        is_final=True,
    )
    second_log = log_interaction(
        agent_id="developer_dex",
        outcome="failure",
        task_summary=summary,
        repo_path=str(repo_path),
        errors=errors,
        session_id="second",
        is_final=True,
    )

    assert os.path.exists(first_log)
    assert os.path.exists(second_log)

    backlog = BacklogManager(str(repo_path)).load_backlog()
    failure_items = [item for item in backlog if item["id"] == expected_id]
    assert len(failure_items) == 1
    assert failure_items[0]["occurrences"] == 2
    assert failure_items[0]["last_session_id"] == "second"
    assert failure_items[0]["status"] == "todo"


def test_failure_log_reopens_in_progress_crash_task(tmp_path):
    repo_path = tmp_path / "repo"
    repo_path.mkdir()
    errors = ["RuntimeError: boom"]
    summary = "Agent execution failed: RuntimeError: boom"
    expected_id = failure_backlog_task_id("developer_dex", summary, errors)

    log_interaction(
        agent_id="developer_dex",
        outcome="failure",
        task_summary=summary,
        repo_path=str(repo_path),
        errors=errors,
        session_id="first",
        is_final=True,
    )
    bm = BacklogManager(str(repo_path))
    assert bm.update_task(expected_id, {"status": "in_progress"})

    log_interaction(
        agent_id="developer_dex",
        outcome="failure",
        task_summary=summary,
        repo_path=str(repo_path),
        errors=errors,
        session_id="second",
        is_final=True,
    )

    task = bm.get_task(expected_id)
    assert task["status"] == "todo"
    assert task["occurrences"] == 2


def test_session_crash_records_blocked_state_and_backlog_id(tmp_path, monkeypatch):
    repo_path = tmp_path / "repo"
    (repo_path / ".exegol").mkdir(parents=True)

    class ExplodingAgent:
        def execute(self, _handoff):
            raise RuntimeError("agent blew up")

    monkeypatch.setattr(
        SessionManager,
        "_create_fresh_instance",
        staticmethod(lambda _module, _class, _llm_client: ExplodingAgent()),
    )

    from inference.inference_manager import InferenceManager

    class FakeLLMClient:
        model = "fake"

        def generate(self, prompt, system_instruction=None, json_format=False):
            return ""

    monkeypatch.setattr(InferenceManager, "get_client", staticmethod(lambda provider=None, model=None: FakeLLMClient()))

    manager = SessionManager(log_every_session=True)
    handoff = _signed_handoff(repo_path)
    result = manager.spawn_agent_session("developer_dex", "unused.module", "UnusedAgent", handoff)
    manager.shutdown_monitors()

    assert result.outcome == "failure"
    assert "RuntimeError: agent blew up" in result.errors[0]
    assert "Traceback" in result.errors[1]

    state = json.loads((repo_path / ".exegol" / "fleet_state.json").read_text(encoding="utf-8"))
    assert state["status"] == "blocked"
    assert state["active_agent"] == "developer_dex"
    assert state["retry_available"] is True
    assert state["backlog_item_id"] == result.state_changes["failure_recovery"]["backlog_item_id"]

    backlog = BacklogManager(str(repo_path)).load_backlog()
    assert any(item["id"] == state["backlog_item_id"] for item in backlog)
