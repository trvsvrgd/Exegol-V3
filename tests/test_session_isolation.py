"""Tests for session isolation and context contract enforcement.

Run with:  python -m pytest tests/test_session_isolation.py -v
"""

import os
import sys
import json
import pytest

# Ensure src/ is importable
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from handoff import HandoffContext, SessionResult
from session_manager import SessionManager


# ---------------------------------------------------------------------------
# HandoffContext tests
# ---------------------------------------------------------------------------

class TestHandoffContext:
    """Verify the handoff contract is minimal and immutable."""

    def test_frozen_immutability(self):
        """HandoffContext fields cannot be mutated after creation."""
        ctx = HandoffContext(
            repo_path="/tmp/test_repo",
            agent_id="test_agent",
            task_id="default",
            model_routing="ollama",
            max_steps=10,
        )
        with pytest.raises(AttributeError):
            ctx.repo_path = "/tmp/different"  # type: ignore

    def test_auto_generates_session_id(self):
        ctx = HandoffContext(
            repo_path="/tmp/test_repo",
            agent_id="test_agent",
            task_id="default",
            model_routing="ollama",
            max_steps=10,
        )
        assert ctx.session_id, "session_id should be auto-generated"
        assert len(ctx.session_id) == 12

    def test_auto_generates_timestamp(self):
        ctx = HandoffContext(
            repo_path="/tmp/test_repo",
            agent_id="test_agent",
            task_id="default",
            model_routing="ollama",
            max_steps=10,
        )
        assert ctx.timestamp, "timestamp should be auto-generated"
        assert "T" in ctx.timestamp  # ISO format

    def test_max_handoff_fields(self):
        """HandoffContext should have at most 7 data fields to stay minimal."""
        import dataclasses
        fields = dataclasses.fields(HandoffContext)
        assert len(fields) <= 7, (
            f"HandoffContext has {len(fields)} fields — exceeds the 7-field "
            "contract for minimal context. Remove or consolidate fields."
        )


# ---------------------------------------------------------------------------
# SessionResult tests
# ---------------------------------------------------------------------------

class TestSessionResult:

    def test_to_dict_serializable(self):
        result = SessionResult(
            agent_id="test_agent",
            session_id="abc123",
            outcome="success",
            output_summary="Done.",
        )
        d = result.to_dict()
        # Should be JSON-serializable
        json_str = json.dumps(d)
        assert "test_agent" in json_str
        assert "success" in json_str


# ---------------------------------------------------------------------------
# SessionManager isolation tests
# ---------------------------------------------------------------------------

class TestSessionIsolation:
    """Verify that consecutive sessions share no state."""

    @pytest.fixture
    def tmp_repo(self, tmp_path):
        """Create a minimal repo structure for testing."""
        exegol_dir = tmp_path / ".exegol"
        exegol_dir.mkdir()
        return str(tmp_path)

    def test_no_state_leak_between_sessions(self, tmp_repo):
        """Two sequential sessions of the same agent should not share state."""
        sm = SessionManager(log_every_session=True)

        handoff_1 = HandoffContext(
            repo_path=tmp_repo,
            agent_id="captivating_cameraman",
            task_id="default",
            model_routing="ollama",
            max_steps=10,
        )
        handoff_2 = HandoffContext(
            repo_path=tmp_repo,
            agent_id="captivating_cameraman",
            task_id="default",
            model_routing="ollama",
            max_steps=10,
        )

        result_1 = sm.spawn_agent_session(
            agent_id="captivating_cameraman",
            module_path="agents.captivating_cameraman_agent",
            class_name="CaptivatingCameramanAgent",
            handoff=handoff_1,
        )
        result_2 = sm.spawn_agent_session(
            agent_id="captivating_cameraman",
            module_path="agents.captivating_cameraman_agent",
            class_name="CaptivatingCameramanAgent",
            handoff=handoff_2,
        )

        # Different sessions
        assert result_1.session_id != result_2.session_id
        # Both succeeded independently
        assert result_1.outcome == "success"
        assert result_2.outcome == "success"

    def test_session_log_persisted(self, tmp_repo):
        """SessionManager should write a log file for each execution."""
        sm = SessionManager(log_every_session=True)

        handoff = HandoffContext(
            repo_path=tmp_repo,
            agent_id="captivating_cameraman",
            task_id="default",
            model_routing="ollama",
            max_steps=10,
        )

        result = sm.spawn_agent_session(
            agent_id="captivating_cameraman",
            module_path="agents.captivating_cameraman_agent",
            class_name="CaptivatingCameramanAgent",
            handoff=handoff,
        )

        log_file = os.path.join(
            tmp_repo, ".exegol", "interaction_logs", f"{result.session_id}.json"
        )
        assert os.path.exists(log_file), "Session log should be persisted"

        with open(log_file, "r") as f:
            log_data = json.load(f)
        assert log_data["agent_id"] == "captivating_cameraman"
        assert log_data["outcome"] == "success"

    def test_unique_session_ids(self, tmp_repo):
        """Every handoff should produce a unique session_id."""
        ids = set()
        for _ in range(10):
            ctx = HandoffContext(
                repo_path=tmp_repo,
                agent_id="test",
                task_id="default",
                model_routing="ollama",
                max_steps=5,
            )
            ids.add(ctx.session_id)
        assert len(ids) == 10, "All 10 session IDs should be unique"
