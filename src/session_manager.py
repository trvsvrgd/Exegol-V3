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
import hmac
import hashlib
from typing import Optional, Any, Dict

from handoff import HandoffContext, SessionResult
from tools.heartbeat_monitor import HeartbeatMonitor


class SessionManager:
    """Spawns agent sessions with full context isolation."""

    def __init__(self, log_every_session: bool = True):
        self.log_every_session = log_every_session
        self._last_executions: Dict[str, float] = {}  # agent_id -> timestamp
        self._default_cooldown = 30.0  # seconds
        # Heartbeat monitors keyed by repo_path (lazy-created per repo)
        self._heartbeat_monitors: Dict[str, HeartbeatMonitor] = {}

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
            Registry key (e.g. ``"developer_dex"``).
        module_path : str
            Dotted module path (e.g. ``"agents.developer_dex_agent"``).
        class_name : str
            Class to instantiate (e.g. ``"DeveloperDexAgent"``).
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

        # --- SECURITY GUARD: Trust System (feat_agent_trust_system) ---
        from tools.trust_manager import TrustManager
        autonomy_level = TrustManager.check_autonomy(agent_id)
        if autonomy_level == "SUSPENDED":
            msg = f"Agent '{agent_id}' is SUSPENDED due to low trust score ({TrustManager.get_score(agent_id)})."
            result.outcome = "failure"
            result.errors.append(msg)
            result.output_summary = "Security Block: Agent suspended."
            print(f"[SessionManager] SECURITY: {msg}")
            return result
        
        # --- SECURITY GUARD: Rate Limiting (sec_sec_arch_002) ---
        cooldown = self._get_agent_cooldown(agent_id, handoff.repo_path)
        last_run = self._last_executions.get(agent_id, 0.0)
        now = time.time()
        
        if now - last_run < cooldown:
            remaining = int(cooldown - (now - last_run))
            msg = f"Rate limit hit for agent '{agent_id}'. Cooldown in effect for {remaining}s."
            result.outcome = "failure"
            result.errors.append(msg)
            result.output_summary = "Security Block: Rate limit exceeded."
            print(f"[SessionManager] SECURITY: {msg}")
            return result
            
        self._last_executions[agent_id] = now

        print(
            f"[SessionManager] Spawning isolated session "
            f"{handoff.session_id} for {class_name}"
        )
        print(
            f"[SessionManager] Handoff -> repo={handoff.repo_path}, "
            f"model={handoff.model_routing}, max_steps={handoff.max_steps}"
        )

        # --- SECURITY GUARD: HMAC Validation (sec_sec_arch_005) ---
        if not self._validate_handoff_signature(handoff):
            result.outcome = "failure"
            result.errors.append("Invalid or missing handoff signature (potential forgery).")
            result.output_summary = "Security Block: Handoff validation failed."
            print(f"[SessionManager] SECURITY: Rejected forged handoff for session {handoff.session_id}")
            return result

        from inference.inference_manager import InferenceManager
        llm_client = InferenceManager.get_client(provider=handoff.model_routing)

        agent_instance = None
        start_time = time.time()

        # --- HEARTBEAT: Register session for zombie detection (arch_agent_heartbeat) ---
        repo_path = handoff.repo_path
        if repo_path not in self._heartbeat_monitors:
            self._heartbeat_monitors[repo_path] = HeartbeatMonitor(repo_path)
        heartbeat = self._heartbeat_monitors[repo_path]
        heartbeat.start(session_id=handoff.session_id, agent_id=agent_id)

        try:
            # 1. Fresh import + instantiation — no cached instances
            agent_instance = self._create_fresh_instance(module_path, class_name, llm_client)

            # 2. Execute with the standardised handoff contract
            os.environ["EXEGOL_ACTIVE_AGENT"] = agent_id
            output = agent_instance.execute(handoff)
            os.environ.pop("EXEGOL_ACTIVE_AGENT", None)

            result.outcome = "success"
            result.output_summary = str(output) if output else ""
            result.steps_used = getattr(agent_instance, "_steps_used", 1)
            
            # Extract autonomous handoff request and snapshots if present
            next_id = getattr(agent_instance, "next_agent_id", "")
            if next_id:
                result.next_agent_id = next_id
                print(f"[SessionManager] Agent {agent_id} requested handoff to: {next_id}")
            
            result.snapshot_hash = getattr(agent_instance, "snapshot_hash", "")
            if result.snapshot_hash:
                print(f"[SessionManager] Snapshot hash captured: {result.snapshot_hash}")

            result.regression_context = getattr(agent_instance, "regression_context", "")
            if result.regression_context:
                print(f"[SessionManager] Regression context captured: {result.regression_context}")

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

            # --- HEARTBEAT: Deregister session on completion or failure ---
            heartbeat.stop(handoff.session_id)

            print(
                f"[SessionManager] Session {handoff.session_id} finished: "
                f"{result.outcome} in {elapsed:.2f}s"
            )

        # 4. Persist interaction log
        if self.log_every_session:
            self._persist_session_log(handoff.repo_path, result)

        return result

    def shutdown_monitors(self) -> None:
        """Stop all heartbeat monitor watchdog threads. Call during orchestrator shutdown."""
        for monitor in self._heartbeat_monitors.values():
            monitor.stop_watchdog()
        self._heartbeat_monitors.clear()
        print("[SessionManager] All heartbeat monitors shut down.")

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
    def _validate_handoff_signature(handoff: HandoffContext) -> bool:
        """Verifies the HMAC signature of the handoff to ensure integrity."""
        secret = os.getenv("EXEGOL_HMAC_SECRET", "dev-secret-keep-it-safe")
        
        # We need to compute the signature over the fields that matter
        # Excluding the signature field itself obviously
        data = f"{handoff.repo_path}|{handoff.agent_id}|{handoff.session_id}|{handoff.timestamp}"
        
        expected_sig = hmac.new(
            secret.encode(),
            data.encode(),
            hashlib.sha256
        ).hexdigest()
        
        return hmac.compare_digest(handoff.signature, expected_sig)

    def _get_agent_cooldown(self, agent_id: str, repo_path: str) -> float:
        """Retrieves the cooldown period for an agent from config."""
        # Try to load from repo-specific config first (not implemented yet in priority.json)
        # Fallback to global settings
        priority_path = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "config", "priority.json")
        if os.path.exists(priority_path):
            try:
                with open(priority_path, "r", encoding="utf-8") as f:
                    config = json.load(f)
                global_settings = config.get("global_settings", {})
                rate_limits = global_settings.get("rate_limits", {})
                return float(rate_limits.get(agent_id, rate_limits.get("default", self._default_cooldown)))
            except Exception:
                pass
        return self._default_cooldown

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
