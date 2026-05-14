"""Handoff contract for context-isolated agent sessions.

Every agent execution receives a frozen HandoffContext and returns a
SessionResult.  These two dataclasses are the *only* interface between
the orchestrator/session-manager and individual agents.  By keeping the
contract minimal, agents can succeed with zero accumulated chat memory —
they read everything they need from the filesystem paths referenced in
the handoff.
"""

import uuid
import datetime
from dataclasses import dataclass, field
from typing import List, Dict, Any


@dataclass(frozen=True)
class HandoffContext:
    """Immutable context passed to an agent at session start.

    Fields are intentionally minimal — the agent must derive any
    additional state from the filesystem (e.g. reading .exegol/backlog.json).
    """

    repo_path: str          # Absolute path to the target repository
    agent_id: str           # Registry key (e.g. "developer_dex")
    task_id: str            # Specific task identifier, or "default"
    model_routing: str      # "ollama" | "gemini"
    max_steps: int          # Step budget for this session
    session_id: str = ""    # Unique execution ID — auto-generated if empty
    timestamp: str = ""     # ISO-8601 invocation time — auto-filled if empty
    snapshot_hash: str = "" # Hash of the codebase state from previous session
    regression_context: str = "" # Optional details if re-triggered due to failure
    loop_depth: int = 0      # Current depth in an autonomous handoff chain
    chain_history: List[str] = field(default_factory=list) # Sequence of agent IDs in the chain
    scheduled_prompt: str = "" # Optional prompt from the scheduler
    signature: str = ""     # HMAC-SHA256 signature for integrity validation

    def __post_init__(self):
        # frozen=True prevents normal assignment; use object.__setattr__
        if not self.session_id:
            object.__setattr__(self, "session_id", uuid.uuid4().hex[:12])
        if not self.timestamp:
            object.__setattr__(
                self, "timestamp",
                datetime.datetime.now().isoformat(timespec="seconds")
            )


@dataclass
class SessionResult:
    """Structured output produced after an agent session completes."""

    agent_id: str
    session_id: str
    outcome: str = "unknown"          # "success" | "failure" | "timeout"
    steps_used: int = 0
    duration_seconds: float = 0.0
    output_summary: str = ""          # Short human-readable result text
    artifacts_written: List[str] = field(default_factory=list)
    errors: List[str] = field(default_factory=list)
    status_update: str = ""           # "idle", "active", or "blocked"
    next_agent_id: str = ""           # ID of the agent that should be triggered next (autonomous chaining)
    snapshot_hash: str = ""           # SHA-256 hash of the codebase state after modifications
    token_usage: int = 0
    prompt_count: int = 0
    monologue: List[Dict[str, Any]] = field(default_factory=list)
    regression_context: str = ""      # Details captured for failure analysis/retry

    def to_dict(self) -> dict:
        """Serialize for JSON persistence in interaction_logs/."""
        return {
            "agent_id": self.agent_id,
            "session_id": self.session_id,
            "outcome": self.outcome,
            "steps_used": self.steps_used,
            "duration_seconds": round(self.duration_seconds, 3),
            "output_summary": self.output_summary,
            "artifacts_written": self.artifacts_written,
            "errors": self.errors,
            "status_update": self.status_update,
            "next_agent_id": self.next_agent_id,
            "snapshot_hash": self.snapshot_hash,
            "regression_context": self.regression_context,
            "token_usage": self.token_usage,
            "prompt_count": self.prompt_count,
            "monologue": self.monologue,
            "timestamp": datetime.datetime.now().isoformat(timespec="seconds")
        }
