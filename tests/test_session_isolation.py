"""Tests for session isolation and context contract enforcement.

Run with:  python -m pytest tests/test_session_isolation.py -v
"""

import os
import sys
import json
import pytest

# Ensure src/ is importable
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

import hmac
import hashlib
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
        """HandoffContext should stay lean — ceiling is 13 fields.

        Field lineage:
        - Original contract: 9 fields.
        - loop_depth, chain_history added by loop-guard sprint (circuit-breaker).
        - scheduled_prompt added by scheduler sprint (HITL-gate prompts).
        - signature added by HMAC security sprint.
        Any future additions must justify themselves against the minimal-context principle.
        """
        import dataclasses
        fields = dataclasses.fields(HandoffContext)
        assert len(fields) <= 13, (
            f"HandoffContext has {len(fields)} fields — exceeds the 13-field "
            "contract. Remove or consolidate fields before adding more."
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

    def _sign_handoff(self, handoff: HandoffContext) -> HandoffContext:
        """Helper to sign handoff for testing."""
        secret = os.getenv("EXEGOL_HMAC_SECRET", "dev-secret-keep-it-safe")
        data = f"{handoff.repo_path}|{handoff.agent_id}|{handoff.session_id}|{handoff.timestamp}"
        signature = hmac.new(secret.encode(), data.encode(), hashlib.sha256).hexdigest()
        object.__setattr__(handoff, "signature", signature)
        return handoff

    def test_no_state_leak_between_sessions(self, tmp_repo):
        """Two sequential sessions of the same agent should not share state."""
        sm = SessionManager(log_every_session=True)

        handoff_1 = HandoffContext(
            repo_path=tmp_repo,
            agent_id="markdown_mace",
            task_id="default",
            model_routing="ollama",
            max_steps=10,
        )
        handoff_2 = HandoffContext(
            repo_path=tmp_repo,
            agent_id="markdown_mace",
            task_id="default",
            model_routing="ollama",
            max_steps=10,
        )

        handoff_1 = self._sign_handoff(handoff_1)
        handoff_2 = self._sign_handoff(handoff_2)

        from unittest.mock import patch
        with patch.object(sm, "_get_agent_cooldown", return_value=0.0):
            result_1 = sm.spawn_agent_session(
                agent_id="markdown_mace",
                module_path="agents.markdown_mace_agent",
                class_name="MarkdownMaceAgent",
                handoff=handoff_1,
            )
            result_2 = sm.spawn_agent_session(
                agent_id="markdown_mace",
                module_path="agents.markdown_mace_agent",
                class_name="MarkdownMaceAgent",
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
            agent_id="markdown_mace",
            task_id="default",
            model_routing="ollama",
            max_steps=10,
        )

        handoff = self._sign_handoff(handoff)

        from unittest.mock import patch
        with patch.object(sm, "_get_agent_cooldown", return_value=0.0):
            result = sm.spawn_agent_session(
                agent_id="markdown_mace",
                module_path="agents.markdown_mace_agent",
                class_name="MarkdownMaceAgent",
                handoff=handoff,
            )

        log_file = os.path.join(
            tmp_repo, ".exegol", "interaction_logs", f"{result.session_id}.json"
        )
        assert os.path.exists(log_file), "Session log should be persisted"

        with open(log_file, "r") as f:
            log_data = json.load(f)
        assert log_data["agent_id"] == "markdown_mace"
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
