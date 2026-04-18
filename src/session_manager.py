"""Session manager — ensures every agent execution is a clean, isolated 'thread'.

Each call to ``spawn_agent_session`` will:
1. Import the agent module and instantiate the class **fresh** (no reuse).
2. Build a minimal HandoffContext from the filesystem only.
3. Execute with step-limit enforcement and timing.
4. Capture the result as a SessionResult, persist it to interaction_logs/.
5. Destroy the agent instance — no state leaks between sessions.
"""

import importlib
import json
import os
import time
import traceback
from typing import Optional, Any

from handoff import HandoffContext, SessionResult


class SessionManager:
    """Spawns agent sessions with full context isolation."""

    def __init__(self, log_every_session: bool = True):
        self.log_every_session = log_every_session

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def spawn_agent_session(
        self,
        agent_id: str,
        module_path: str,
        class_name: str,
        handoff: HandoffContext
    ) -> SessionResult:
        """Execute an agent in an isolated session.

        Parameters
        ----------
        agent_id : str
            Registry key (e.g. ``"developer_dragon"``).
        module_path : str
            Dotted module path (e.g. ``"agents.developer_dragon_agent"``).
        class_name : str
            Class to instantiate (e.g. ``"DeveloperDragonAgent"``).
        handoff : HandoffContext
            Frozen context for this session.

        Returns
        -------
        SessionResult
            Structured outcome of the execution.
        """
        result = SessionResult(
            agent_id=agent_id,
            session_id=handoff.session_id,
        )

        print(
            f"[SessionManager] Spawning isolated session "
            f"{handoff.session_id} for {class_name}"
        )
        print(
            f"[SessionManager] Handoff -> repo={handoff.repo_path}, "
            f"model={handoff.model_routing}, max_steps={handoff.max_steps}"
        )

        from inference.llm_client import LLMClient
        llm_client = LLMClient(provider=handoff.model_routing)

        agent_instance = None
        start_time = time.time()

        try:
            # 1. Fresh import + instantiation — no cached instances
            agent_instance = self._create_fresh_instance(module_path, class_name, llm_client)

            # 2. Execute with the standardised handoff contract
            output = agent_instance.execute(handoff)

            result.outcome = "success"
            result.output_summary = str(output) if output else ""
            result.steps_used = getattr(agent_instance, "_steps_used", 1)

        except Exception as exc:
            result.outcome = "failure"
            result.errors.append(f"{type(exc).__name__}: {exc}")
            result.output_summary = "Agent execution failed."
            traceback.print_exc()

        finally:
            elapsed = time.time() - start_time
            result.duration_seconds = elapsed

            # 3. Destroy the instance — no state retained
            del agent_instance

            print(
                f"[SessionManager] Session {handoff.session_id} finished: "
                f"{result.outcome} in {elapsed:.2f}s"
            )

        # 4. Persist interaction log
        if self.log_every_session:
            self._persist_session_log(handoff.repo_path, result)

        return result

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _create_fresh_instance(module_path: str, class_name: str, llm_client: Any):
        """Import and instantiate agent class without caching."""
        mod = importlib.import_module(module_path)
        # Reload to guarantee no stale state
        importlib.reload(mod)
        cls = getattr(mod, class_name)
        return cls(llm_client=llm_client)

    @staticmethod
    def _persist_session_log(repo_path: str, result: SessionResult) -> Optional[str]:
        """Write the SessionResult to .exegol/interaction_logs/{session_id}.json."""
        logs_dir = os.path.join(repo_path, ".exegol", "interaction_logs")
        os.makedirs(logs_dir, exist_ok=True)

        log_file = os.path.join(logs_dir, f"{result.session_id}.json")
        try:
            with open(log_file, "w", encoding="utf-8") as f:
                json.dump(result.to_dict(), f, indent=4)
            print(f"[SessionManager] Session log persisted -> {log_file}")
            return log_file
        except Exception as exc:
            print(f"[SessionManager] Failed to persist log: {exc}")
            return None
