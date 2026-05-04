"""Heartbeat Monitor — arch_agent_heartbeat implementation.

Provides a lightweight, thread-based heartbeat system for detecting zombie
agent sessions within the Exegol orchestrator. Each active agent session
registers a heartbeat file on disk (inside .exegol/heartbeats/). A background
watchdog thread polls those files and escalates via Slack if a session
exceeds its configured Time-To-Live (TTL) without a fresh pulse.

Usage
-----
    from tools.heartbeat_monitor import HeartbeatMonitor

    monitor = HeartbeatMonitor(repo_path, ttl_seconds=120)
    monitor.start(session_id="abc123", agent_id="developer_dex")

    # ... agent runs ...
    # optionally call monitor.pulse(session_id) from within the agent loop
    # to refresh the heartbeat during long-running tasks.

    monitor.stop(session_id)
"""

import json
import os
import threading
import time
from datetime import datetime
from typing import Dict, Optional


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
_DEFAULT_TTL_SECONDS = 120          # 2 minutes with no pulse = zombie
_WATCHDOG_INTERVAL_SECONDS = 15     # How often the watchdog scans
_HEARTBEAT_DIR_NAME = "heartbeats"  # Relative to .exegol/


class HeartbeatMonitor:
    """Manages heartbeat files for active agent sessions and detects zombies.

    Each session gets a JSON heartbeat file:
        .exegol/heartbeats/<session_id>.json

    The watchdog thread reads all heartbeat files and flags any whose
    ``last_pulse`` timestamp is older than ``ttl_seconds``.

    Parameters
    ----------
    repo_path : str
        Absolute path to the repository root.
    ttl_seconds : int
        Maximum seconds since last pulse before a session is flagged zombie.
    notify_fn : callable, optional
        A function accepting a single ``str`` message to deliver alerts.
        Defaults to a Slack post via ``tools.slack_tool``.
    """

    def __init__(
        self,
        repo_path: str,
        ttl_seconds: int = _DEFAULT_TTL_SECONDS,
        notify_fn=None,
    ):
        self.repo_path = repo_path
        self.ttl_seconds = ttl_seconds
        self._heartbeat_dir = os.path.join(repo_path, ".exegol", _HEARTBEAT_DIR_NAME)
        os.makedirs(self._heartbeat_dir, exist_ok=True)

        # Notification channel (lazy-loaded Slack by default)
        if notify_fn is None:
            try:
                from tools.slack_tool import post_to_slack
                self._notify = post_to_slack
            except ImportError:
                self._notify = print
        else:
            self._notify = notify_fn

        # Watchdog thread state
        self._watchdog_thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()
        self._active_sessions: Dict[str, dict] = {}   # session_id -> metadata
        self._lock = threading.Lock()
        self._alerted_sessions: set = set()            # avoid duplicate alerts

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def start(self, session_id: str, agent_id: str) -> None:
        """Register a new session and start the watchdog (if not already running).

        Parameters
        ----------
        session_id : str
            Unique identifier for this agent session (from HandoffContext).
        agent_id : str
            Human-readable agent name for alert messages.
        """
        metadata = {
            "session_id": session_id,
            "agent_id": agent_id,
            "started_at": datetime.now().isoformat(),
            "last_pulse": datetime.now().isoformat(),
            "status": "active",
        }
        self._write_heartbeat(session_id, metadata)

        with self._lock:
            self._active_sessions[session_id] = metadata

        self._ensure_watchdog_running()
        print(f"[HeartbeatMonitor] Session {session_id} ({agent_id}) registered.")

    def pulse(self, session_id: str) -> None:
        """Refresh the heartbeat timestamp for a running session.

        Should be called periodically by long-running agents to signal
        they are still alive and making progress.

        Parameters
        ----------
        session_id : str
            The session whose heartbeat to refresh.
        """
        with self._lock:
            if session_id not in self._active_sessions:
                return
            self._active_sessions[session_id]["last_pulse"] = datetime.now().isoformat()
            metadata = self._active_sessions[session_id]

        self._write_heartbeat(session_id, metadata)

    def stop(self, session_id: str) -> None:
        """Mark a session as cleanly finished and remove its heartbeat file.

        Parameters
        ----------
        session_id : str
            The session that has completed execution.
        """
        with self._lock:
            self._active_sessions.pop(session_id, None)
            self._alerted_sessions.discard(session_id)

        hb_path = self._heartbeat_path(session_id)
        try:
            if os.path.exists(hb_path):
                os.remove(hb_path)
        except OSError as exc:
            print(f"[HeartbeatMonitor] Warning: Could not remove heartbeat file: {exc}")

        print(f"[HeartbeatMonitor] Session {session_id} cleanly deregistered.")

    def stop_watchdog(self) -> None:
        """Stops the background watchdog thread.  Call during orchestrator shutdown."""
        self._stop_event.set()
        if self._watchdog_thread and self._watchdog_thread.is_alive():
            self._watchdog_thread.join(timeout=5)
        print("[HeartbeatMonitor] Watchdog stopped.")

    def get_active_sessions(self) -> Dict[str, dict]:
        """Return a snapshot of currently tracked sessions."""
        with self._lock:
            return dict(self._active_sessions)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _ensure_watchdog_running(self) -> None:
        """Start the watchdog thread if it isn't already alive."""
        if self._watchdog_thread and self._watchdog_thread.is_alive():
            return
        self._stop_event.clear()
        self._watchdog_thread = threading.Thread(
            target=self._watchdog_loop,
            daemon=True,
            name="HeartbeatWatchdog",
        )
        self._watchdog_thread.start()
        print(f"[HeartbeatMonitor] Watchdog started (TTL={self.ttl_seconds}s, interval={_WATCHDOG_INTERVAL_SECONDS}s).")

    def _watchdog_loop(self) -> None:
        """Continuously scan heartbeat files and flag zombie sessions."""
        while not self._stop_event.is_set():
            self._scan_for_zombies()
            self._stop_event.wait(_WATCHDOG_INTERVAL_SECONDS)

    def _scan_for_zombies(self) -> None:
        """Read heartbeat files from disk and alert on stale sessions."""
        try:
            files = [
                f for f in os.listdir(self._heartbeat_dir)
                if f.endswith(".json")
            ]
        except OSError:
            return

        now = datetime.now()
        for filename in files:
            hb_path = os.path.join(self._heartbeat_dir, filename)
            try:
                with open(hb_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
            except (OSError, json.JSONDecodeError):
                continue

            session_id = data.get("session_id", filename.replace(".json", ""))
            agent_id = data.get("agent_id", "unknown")
            last_pulse_str = data.get("last_pulse", "")

            # Skip if status is not active
            if data.get("status") != "active":
                continue

            try:
                last_pulse = datetime.fromisoformat(last_pulse_str)
            except ValueError:
                continue

            age_seconds = (now - last_pulse).total_seconds()
            if age_seconds > self.ttl_seconds:
                if session_id not in self._alerted_sessions:
                    self._alerted_sessions.add(session_id)
                    self._flag_zombie(session_id, agent_id, age_seconds)

    def _flag_zombie(self, session_id: str, agent_id: str, age_seconds: float) -> None:
        """Log and notify about a zombie session."""
        msg = (
            f"🧟 *Zombie Session Detected!*\n"
            f"  • Agent: `{agent_id}`\n"
            f"  • Session: `{session_id}`\n"
            f"  • Last pulse: `{age_seconds:.0f}s` ago (TTL: {self.ttl_seconds}s)\n"
            f"  • Action: Manual review required. Check for hanging tool calls or deadlocks."
        )
        print(f"[HeartbeatMonitor] ZOMBIE ALERT: {agent_id} / {session_id} — {age_seconds:.0f}s since last pulse.")
        self._notify(msg)

        # Write a security-style zombie event to the heartbeat file for audit
        hb_path = self._heartbeat_path(session_id)
        try:
            with open(hb_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            data["status"] = "zombie"
            data["zombie_detected_at"] = datetime.now().isoformat()
            data["zombie_age_seconds"] = round(age_seconds, 2)
            with open(hb_path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=4)
        except (OSError, json.JSONDecodeError) as exc:
            print(f"[HeartbeatMonitor] Warning: Could not update zombie heartbeat: {exc}")

    def _heartbeat_path(self, session_id: str) -> str:
        return os.path.join(self._heartbeat_dir, f"{session_id}.json")

    def _write_heartbeat(self, session_id: str, metadata: dict) -> None:
        """Atomically write the heartbeat metadata to disk."""
        hb_path = self._heartbeat_path(session_id)
        try:
            with open(hb_path, "w", encoding="utf-8") as f:
                json.dump(metadata, f, indent=4)
        except OSError as exc:
            print(f"[HeartbeatMonitor] Warning: Could not write heartbeat file: {exc}")

    @staticmethod
    def pulse_session(repo_path: str, session_id: str) -> None:
        """Static helper to refresh a heartbeat file without an active monitor instance.
        
        Useful for tools or agents to signal they are alive during long-running operations.
        """
        hb_dir = os.path.join(repo_path, ".exegol", _HEARTBEAT_DIR_NAME)
        hb_path = os.path.join(hb_dir, f"{session_id}.json")
        
        if not os.path.exists(hb_path):
            return
            
        try:
            with open(hb_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            
            data["last_pulse"] = datetime.now().isoformat()
            
            with open(hb_path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=4)
        except (OSError, json.JSONDecodeError):
            pass
