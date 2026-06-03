import json
import os
import time
import threading
import sys
import schedule
import hmac
import hashlib
import traceback
from datetime import datetime, timedelta
from dotenv import load_dotenv

# Load environment variables before any other imports
load_dotenv()

from typing import Dict, Any, List, Optional
from agents.registry import AGENT_REGISTRY
from handoff import HandoffContext, SessionResult
from session_manager import SessionManager
from tools.slack_tool import slack_manager
from tools.fleet_logger import log_interaction
from tools.fleet_runtime_control import (
    request_runtime_stop,
    resume_runtime,
    is_runtime_stopped,
    unload_local_models_async,
)
from tools.state_manager import StateManager
from tools.objective_manager import ObjectiveManager
from tools.zero_to_one_onboarding import activate_zero_to_one_objective, is_zero_to_one_repo, zero_to_one_status

PRIORITY_FILE_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'config', 'priority.json')
HISTORY_FILE_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'config', 'job_history.json')

WEEKDAY_INDEX = {
    "monday": 0,
    "tuesday": 1,
    "wednesday": 2,
    "thursday": 3,
    "friday": 4,
    "saturday": 5,
    "sunday": 6,
}

class ExegolOrchestrator:
    def __init__(self):
        self.priority_config: Dict[str, Any] = {}
        self.load_config()
        self.active_target = self.get_highest_priority_task()
        self.session_manager = SessionManager(
            log_every_session=self._get_isolation_setting("log_every_session", True)
        )
        self.is_running_fleet = False
        self._fleet_cycle_lock = threading.Lock()
        self._fleet_stop_requested = threading.Event()
        self._should_stop_scheduler = False
        self.job_history = self._load_job_history()
        
        # --- SLACK INTEGRATION CHECK ---
        if not slack_manager.bot_token and not slack_manager.webhook_url:
            print("\n" + "!"*60)
            print("CRITICAL WARNING: Slack Integration is OFFLINE.")
            print("Exegol is running in [CONSOLE-ONLY] mode. Interactive approvals and")
            print("remote wake-words will NOT function.")
            print("FIX: See docs/guides/slack_integration_fix.md")
            print("!"*60 + "\n")
        
        # Initialize Slack Listener
        slack_manager.setup_listener(self.handle_wake_word)
        
        # Priority Execution Logic
        self.agent_priority_order = [
            "thoughtful_thrawn", "vibe_vader", "compliance_cody", "security_sabine", 
            "technical_tarkin", "model_router_mothma", "strategist_sloane", "growth_galen", 
            "finance_fennec", "evaluator_ezra", "report_revan", "chief_of_staff_chewie", 
            "optimizer_ahsoka", "architect_artoo", "watcher_wedge", "quality_quigon", 
            "product_poe", "developer_dex", "uat_ulic", "intel_ima", "markdown_mace"
        ]
        self.pending_tasks = []
        self.queue_condition = threading.Condition()
        self.current_running_agent = None
        
        # Initialize Autonomous Cadence Engine unless startup explicitly disables it.
        if os.getenv("EXEGOL_DISABLE_SCHEDULER", "").lower() in {"1", "true", "yes"}:
            print("[Scheduler] Disabled by EXEGOL_DISABLE_SCHEDULER.")
        else:
            self._setup_cadence_engine()

    def get_agent_priority(self, agent_id):
        order = getattr(self, "agent_priority_order", [])
        try:
            return order.index(agent_id)
        except ValueError:
            return 999

    def _fleet_stop_event(self) -> threading.Event:
        """Return a lazily-created cooperative stop event for fleet cycles."""
        event = getattr(self, "_fleet_stop_requested", None)
        if event is None:
            event = threading.Event()
            self._fleet_stop_requested = event
        return event

    def request_fleet_stop(self, reason: str = "manual stop requested") -> bool:
        """Request the active fleet cycle to stop before any further dispatch."""
        event = self._fleet_stop_event()
        event.set()
        request_runtime_stop(reason)
        unload_local_models_async(reason)
        was_running = bool(getattr(self, "is_running_fleet", False))
        self.is_running_fleet = False
        with self.queue_condition:
            self.queue_condition.notify_all()
        print(f"[Orchestrator] Fleet stop requested: {reason}")
        return was_running

    def clear_fleet_stop_request(self) -> None:
        self._fleet_stop_event().clear()

    def is_fleet_stop_requested(self) -> bool:
        return self._fleet_stop_event().is_set()

    def acquire_execution_lock(self, agent_id):
        priority = self.get_agent_priority(agent_id)
        import uuid
        ticket = {"id": str(uuid.uuid4()), "priority": priority, "agent_id": agent_id}
        
        with self.queue_condition:
            self.pending_tasks.append(ticket)
            self.pending_tasks.sort(key=lambda x: x["priority"])
            while self.current_running_agent is not None or self.pending_tasks[0]["id"] != ticket["id"]:
                if self.is_fleet_stop_requested():
                    self.pending_tasks = [item for item in self.pending_tasks if item["id"] != ticket["id"]]
                    self.queue_condition.notify_all()
                    print(f"[Orchestrator] Stop requested; abandoning queued wake for {agent_id}.")
                    return False
                self.queue_condition.wait(timeout=0.5)
            if self.is_fleet_stop_requested():
                self.pending_tasks = [item for item in self.pending_tasks if item["id"] != ticket["id"]]
                self.queue_condition.notify_all()
                print(f"[Orchestrator] Stop requested; refusing wake for {agent_id}.")
                return False
            self.current_running_agent = ticket
            self.pending_tasks.pop(0)
            return True

    def release_execution_lock(self):
        with self.queue_condition:
            self.current_running_agent = None
            self.queue_condition.notify_all()

    def _setup_cadence_engine(self):
        """Configures periodic autonomous tasks for the fleet from config."""
        if os.getenv("EXEGOL_DISABLE_SCHEDULER_FOR_TESTS") == "1":
            print("[Scheduler] Disabled by EXEGOL_DISABLE_SCHEDULER_FOR_TESTS.")
            self._write_scheduler_state("disabled", detail="disabled by EXEGOL_DISABLE_SCHEDULER_FOR_TESTS")
            return

        if getattr(self, "scheduler_thread", None) and self.scheduler_thread.is_alive():
            self._write_scheduler_state("healthy", detail="scheduler already running")
            return

        cadence_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "config", "fleet_cadence.json")
        if not os.path.exists(cadence_path):
            print("[Scheduler] No fleet_cadence.json found. Skipping cadence engine.")
            self._write_scheduler_state("disabled", detail="config/fleet_cadence.json missing")
            return

        try:
            with open(cadence_path, "r", encoding="utf-8") as f:
                config = json.load(f)
            
            if not config.get("global_settings", {}).get("enable_scheduler", True):
                print("[Scheduler] Scheduler disabled in config.")
                self._write_scheduler_state("disabled", detail="disabled in config/fleet_cadence.json")
                return

            schedule.clear("exegol")
            for job in config.get("schedules", []):
                if not job.get("enabled", True):
                    continue
                
                freq = job.get("frequency")
                at_time = job.get("at")
                agent_id = job.get("agent_id")
                summary = job.get("summary")

                # Map frequency string to schedule methods
                s = schedule.every()
                if freq == "daily":
                    s = s.day
                elif freq == "monday":
                    s = s.monday
                elif freq == "tuesday":
                    s = s.tuesday
                elif freq == "wednesday":
                    s = s.wednesday
                elif freq == "thursday":
                    s = s.thursday
                elif freq == "friday":
                    s = s.friday
                elif freq == "saturday":
                    s = s.saturday
                elif freq == "sunday":
                    s = s.sunday
                elif freq == "monthly":
                    # schedule doesn't have .monthly(), but we can do every(30).days as a proxy
                    # or better, just use every(4).weeks
                    s = s.weeks
                    val = 4
                    s = schedule.every(val).weeks
                elif freq.startswith("every_"):
                    # e.g. every_10_minutes
                    parts = freq.split("_")
                    val = int(parts[1])
                    unit = parts[2]
                    if "minute" in unit: s = schedule.every(val).minutes
                    elif "hour" in unit: s = schedule.every(val).hours
                    elif "day" in unit: s = schedule.every(val).days
                    elif "week" in unit: s = schedule.every(val).weeks
                
                if at_time:
                    s = s.at(at_time)
                
                s.do(self._scheduled_trigger, agent_id=agent_id, summary=summary, job_id=job.get("id")).tag("exegol")
                print(f"[Scheduler] Registered: {summary} ({agent_id}) @ {freq} {at_time or ''}")

            # Check for missed jobs
            self._check_for_missed_jobs(config)

            # Start Scheduler Thread
            self._check_interval = config.get("global_settings", {}).get("check_interval_seconds", 60)
            self.scheduler_thread = threading.Thread(target=self._run_scheduler, daemon=True)
            self.scheduler_thread.start()
            self._write_scheduler_state("healthy", detail="scheduler started", registered_jobs=len(schedule.get_jobs("exegol")))
            print(f"[Scheduler] Cadence engine started (interval: {self._check_interval}s).")

        except Exception as e:
            print(f"[Scheduler] Error setting up cadence engine: {e}")
            self._write_scheduler_state("degraded", detail=str(e))

    def _run_scheduler(self):
        while not self._should_stop_scheduler:
            self._write_scheduler_state("healthy", detail="heartbeat", registered_jobs=len(schedule.get_jobs("exegol")))
            schedule.run_pending()
            time.sleep(self._check_interval)
        self._write_scheduler_state("stopped", detail="scheduler stop requested")

    def restart_scheduler(self) -> bool:
        """Restart the in-process cadence scheduler after supervisor detects a dead thread."""
        if os.getenv("EXEGOL_DISABLE_SCHEDULER", "").lower() in {"1", "true", "yes"}:
            return False

        existing = getattr(self, "scheduler_thread", None)
        if existing and existing.is_alive():
            return True

        self._should_stop_scheduler = False
        try:
            schedule.clear()
        except Exception as exc:
            print(f"[Scheduler] Failed to clear stale scheduler jobs before restart: {exc}")

        self._setup_cadence_engine()
        restarted = getattr(self, "scheduler_thread", None)
        return bool(restarted and restarted.is_alive())

    def _load_job_history(self) -> Dict[str, str]:
        history_path = getattr(self, "job_history_path", HISTORY_FILE_PATH)
        if os.path.exists(history_path):
            try:
                with open(history_path, "r", encoding="utf-8") as f:
                    return json.load(f)
            except:
                return {}
        return {}

    def _save_job_history(self):
        try:
            history_path = getattr(self, "job_history_path", HISTORY_FILE_PATH)
            with open(history_path, "w", encoding="utf-8") as f:
                json.dump(self.job_history, f, indent=4)
        except Exception as e:
            print(f"[Scheduler] Failed to save job history: {e}")

    def _load_cadence_config(self) -> Dict[str, Any]:
        cadence_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "config", "fleet_cadence.json")
        if not os.path.exists(cadence_path):
            return {}
        try:
            with open(cadence_path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as exc:
            print(f"[Scheduler] Failed to load cadence config: {exc}")
            return {}

    @staticmethod
    def _parse_history_timestamp(value: Optional[str]) -> Optional[datetime]:
        if not value:
            return None
        try:
            return datetime.fromisoformat(value)
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _parse_at_time(at_time: Optional[str]) -> tuple[int, int]:
        if not at_time:
            return 0, 0
        try:
            hh, mm = map(int, str(at_time).split(":", 1))
            return hh, mm
        except (TypeError, ValueError):
            return 0, 0

    @staticmethod
    def _interval_delta(frequency: str) -> Optional[timedelta]:
        if not frequency.startswith("every_"):
            return None
        parts = frequency.split("_")
        if len(parts) < 3:
            return None
        try:
            value = int(parts[1])
        except ValueError:
            return None
        unit = parts[2]
        if "minute" in unit:
            return timedelta(minutes=value)
        if "hour" in unit:
            return timedelta(hours=value)
        if "day" in unit:
            return timedelta(days=value)
        if "week" in unit:
            return timedelta(weeks=value)
        return None

    def _daily_boundary(self, now: datetime, at_time: Optional[str]) -> datetime:
        hh, mm = self._parse_at_time(at_time)
        boundary = now.replace(hour=hh, minute=mm, second=0, microsecond=0)
        if boundary > now:
            boundary -= timedelta(days=1)
        return boundary

    def _latest_weekday_boundary(self, now: datetime, weekday_name: str, at_time: Optional[str]) -> datetime:
        hh, mm = self._parse_at_time(at_time)
        weekday_index = WEEKDAY_INDEX[weekday_name]
        days_since = (now.weekday() - weekday_index) % 7
        boundary = (now - timedelta(days=days_since)).replace(hour=hh, minute=mm, second=0, microsecond=0)
        if boundary > now:
            boundary -= timedelta(days=7)
        return boundary

    def _latest_monthly_boundary(self, now: datetime, at_time: Optional[str]) -> datetime:
        hh, mm = self._parse_at_time(at_time)
        boundary = now.replace(day=1, hour=hh, minute=mm, second=0, microsecond=0)
        if boundary <= now:
            return boundary
        previous_month = now.month - 1 or 12
        previous_year = now.year - 1 if now.month == 1 else now.year
        return boundary.replace(year=previous_year, month=previous_month)

    def _scheduled_due_reason(
        self,
        job: Dict[str, Any],
        last_run: Optional[datetime],
        now: datetime,
        trigger_source: str,
    ) -> Optional[str]:
        frequency = str(job.get("frequency", ""))
        at_time = job.get("at")

        if last_run is None:
            if trigger_source == "startup":
                return None
            return "No recorded run history"

        if frequency == "daily":
            boundary = self._daily_boundary(now, at_time)
            if now >= boundary and last_run < boundary:
                return f"Missed daily run due {boundary.isoformat()}"
            return None

        if frequency in WEEKDAY_INDEX:
            boundary = self._latest_weekday_boundary(now, frequency, at_time)
            if last_run < boundary:
                return f"Missed {frequency} {at_time or 'weekly'} run"
            return None

        if frequency == "monthly":
            boundary = self._latest_monthly_boundary(now, at_time)
            if last_run < boundary:
                return f"Missed monthly run due {boundary.isoformat()}"
            return None

        delta = self._interval_delta(frequency)
        if delta and (now - last_run) >= delta:
            return f"Missed interval run (last run: {last_run.isoformat()})"

        return None

    def plan_due_scheduled_jobs(
        self,
        config: Optional[Dict[str, Any]] = None,
        now: Optional[datetime] = None,
        trigger_source: str = "manual_run",
        initialize_missing: bool = False,
    ) -> List[Dict[str, Any]]:
        """Return enabled cadence jobs that are due or missed, ordered for execution."""
        config = config if config is not None else self._load_cadence_config()
        now = now or datetime.now()
        due_jobs: List[Dict[str, Any]] = []

        for index, job in enumerate(config.get("schedules", [])):
            if not job.get("enabled", True):
                continue
            if trigger_source == "manual_run" and not job.get("catch_up_on_manual_run", True):
                continue

            job_id = job.get("id")
            if not job_id:
                continue

            last_run_raw = self.job_history.get(job_id)
            last_run = self._parse_history_timestamp(last_run_raw)
            if not last_run_raw and initialize_missing:
                self.job_history[job_id] = now.isoformat()
                continue

            reason = self._scheduled_due_reason(job, last_run, now, trigger_source)
            if not reason:
                continue

            planned = dict(job)
            planned["_index"] = index
            planned["due_reason"] = reason
            planned["last_run"] = last_run_raw
            due_jobs.append(planned)

        def sort_key(job: Dict[str, Any]) -> tuple[int, int, int]:
            try:
                run_order = int(job.get("run_order", job.get("_index", 999)))
            except (TypeError, ValueError):
                run_order = int(job.get("_index", 999))
            return (run_order, self.get_agent_priority(job.get("agent_id", "")), int(job.get("_index", 999)))

        return sorted(due_jobs, key=sort_key)

    def _check_for_missed_jobs(self, config):
        """Checks if any jobs should have run while the fleet was down."""
        now = datetime.now()
        max_missed = int(config.get("global_settings", {}).get("max_missed_jobs_on_startup", 3))
        triggered_missed = 0

        due_jobs = self.plan_due_scheduled_jobs(
            config=config,
            now=now,
            trigger_source="startup",
            initialize_missing=True,
        )

        for job in due_jobs:
            job_id = job.get("id")
            reason = job.get("due_reason", "missed scheduled run")
            if triggered_missed >= max_missed:
                self._record_scheduler_event("missed_job_skipped", job_id, f"startup cap reached: {max_missed}")
                continue
            print(f"[Scheduler] Detected missed job: {job.get('summary')} ({job_id}). {reason}.")
            triggered_missed += 1
            self._record_scheduler_event("missed_job_triggered", job_id, reason)
            if os.getenv("EXEGOL_DEFER_MISSED_JOBS") == "1":
                self._record_scheduler_event("missed_job_deferred", job_id, "deferred during backend startup")
                continue
            self._scheduled_trigger(job.get("agent_id"), f"[MISSED] {job.get('summary')}", job_id)

        self._save_job_history()

    def _scheduled_trigger(self, agent_id: str, summary: str, job_id: str = None):
        """Bridge between schedule library and the orchestration loop."""
        if is_runtime_stopped():
            self._record_scheduler_event("scheduled_job_skipped", job_id or agent_id, "fleet runtime is stopped")
            return

        def run_task():
            self._run_scheduled_task(agent_id=agent_id, summary=summary, job_id=job_id)

        threading.Thread(target=run_task, daemon=True).start()

    def _run_scheduled_task(
        self,
        agent_id: str,
        summary: str,
        job_id: str = None,
        target: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        print(f"\n[Scheduler] Triggering scheduled task: {summary} ({agent_id})")
        if is_runtime_stopped():
            print("[Scheduler] Fleet runtime is stopped; skipping scheduled task.")
            return {"status": "skipped", "reason": "fleet runtime stopped", "job_id": job_id, "agent_id": agent_id}
        target = target or self.active_target or self.get_highest_priority_task()
        if not target:
            print("[Scheduler] No target repository found for scheduled task.")
            return {"status": "skipped", "reason": "no target repository", "job_id": job_id}

        routing = target.get("model_routing_preference", "ollama")
        entry = AGENT_REGISTRY.get(agent_id)
        if not entry:
            print(f"[Scheduler] Error: Scheduled agent '{agent_id}' not found in registry.")
            return {"status": "skipped", "reason": "unknown agent", "job_id": job_id, "agent_id": agent_id}

        try:
            slack_manager.post_message(f"Scheduled Task: {summary}. Waking `{agent_id}`...")
        except Exception as exc:
            self._record_scheduler_event("slack_notify_failed", job_id or agent_id, f"{type(exc).__name__}: {exc}")

        status = "completed"
        result_summary: Dict[str, Any] = {}
        try:
            result = self.wake_and_execute_agent(
                repo_info=target,
                routing=routing,
                max_steps=20,
                agent_id=agent_id,
                scheduled_prompt=summary
            )
            result_summary = {
                "outcome": getattr(result, "outcome", None),
                "session_id": getattr(result, "session_id", None),
                "next_agent_id": getattr(result, "next_agent_id", ""),
            }
        except Exception as exc:
            status = "failed"
            result_summary = {"error": f"{type(exc).__name__}: {exc}"}
            self._record_scheduler_event("job_failed", job_id or agent_id, result_summary["error"])
        finally:
            if job_id:
                self.job_history[job_id] = datetime.now().isoformat()
                self._save_job_history()
                event_type = "job_completed" if status == "completed" else "job_attempted_with_failure"
                self._record_scheduler_event(event_type, job_id, summary)

        return {
            "status": status,
            "job_id": job_id,
            "agent_id": agent_id,
            "summary": summary,
            "result": result_summary,
        }

    def run_due_scheduled_agents(
        self,
        repo_path: Optional[str] = None,
        trigger_source: str = "manual_run",
        now: Optional[datetime] = None,
    ) -> Dict[str, Any]:
        """Run due cadence jobs before a manual/autonomous fleet cycle."""
        config = self._load_cadence_config()
        if not config or not config.get("global_settings", {}).get("enable_scheduler", True):
            return {"status": "disabled", "due_count": 0, "triggered_count": 0, "jobs": []}

        due_jobs = self.plan_due_scheduled_jobs(
            config=config,
            now=now,
            trigger_source=trigger_source,
            initialize_missing=False,
        )
        settings = config.get("global_settings", {})
        max_jobs_raw = settings.get("max_due_jobs_on_run_fleet", len(due_jobs))
        try:
            max_jobs = int(max_jobs_raw)
        except (TypeError, ValueError):
            max_jobs = len(due_jobs)

        target = self._repo_info_for_path(repo_path) if repo_path else (self.active_target or self.get_highest_priority_task())
        results: List[Dict[str, Any]] = []
        for index, job in enumerate(due_jobs):
            job_id = job.get("id")
            if max_jobs >= 0 and index >= max_jobs:
                self._record_scheduler_event(
                    "manual_due_job_skipped",
                    job_id,
                    f"manual run cap reached: {max_jobs}",
                )
                results.append({
                    "status": "skipped",
                    "job_id": job_id,
                    "agent_id": job.get("agent_id"),
                    "reason": f"manual run cap reached: {max_jobs}",
                })
                continue

            reason = job.get("due_reason", "scheduled job due")
            self._record_scheduler_event("manual_due_job_triggered", job_id, reason)
            result = self._run_scheduled_task(
                agent_id=job.get("agent_id"),
                summary=f"[DUE] {job.get('summary')}",
                job_id=job_id,
                target=target,
            )
            result["due_reason"] = reason
            results.append(result)

        return {
            "status": "success",
            "due_count": len(due_jobs),
            "triggered_count": len([item for item in results if item.get("status") != "skipped"]),
            "jobs": results,
        }

    def _write_scheduler_state(self, status: str, detail: str = "", registered_jobs: Optional[int] = None):
        target = self.active_target or {"repo_path": os.path.dirname(os.path.dirname(__file__))}
        repo_path = target.get("repo_path") or os.path.dirname(os.path.dirname(__file__))
        now = datetime.now().isoformat()
        state = {
            "schema_version": 1,
            "status": status,
            "detail": detail,
            "registered_jobs": registered_jobs,
            "enabled": status != "disabled",
            "heartbeat": now if status == "healthy" else None,
            "updated_at": now,
        }
        StateManager(repo_path).write_json(getattr(self, "scheduler_state_file", ".exegol/scheduler_state.json"), state)

    def _record_scheduler_event(self, event_type: str, job_id: str, detail: str):
        target = self.active_target or {"repo_path": os.path.dirname(os.path.dirname(__file__))}
        repo_path = target.get("repo_path") or os.path.dirname(os.path.dirname(__file__))
        sm = StateManager(repo_path)
        events = sm.read_json(".exegol/scheduler_events.json") or []
        events.append({
            "timestamp": datetime.now().isoformat(),
            "event_type": event_type,
            "job_id": job_id,
            "detail": detail,
        })
        sm.write_json(".exegol/scheduler_events.json", events)

    def load_config(self):
        """Loads priority and agent configuration from priority.json"""
        if os.path.exists(PRIORITY_FILE_PATH):
            with open(PRIORITY_FILE_PATH, 'r') as f:
                self.priority_config = json.load(f)
            print("Configuration loaded successfully.")
        else:
            print(f"Warning: Configuration file not found at {PRIORITY_FILE_PATH}")

    def update_repo_status(self, repo_path: str, new_status: str):
        """Updates the agent_status for a given repository in priority.json."""
        updated = False
        for repo in self.priority_config.get("repositories", []):
            if repo.get("repo_path") == repo_path:
                if repo.get("agent_status") != new_status:
                    repo["agent_status"] = new_status
                    updated = True
                break
        
        if updated:
            try:
                with open(PRIORITY_FILE_PATH, 'w') as f:
                    json.dump(self.priority_config, f, indent=2)
                print(f"[Status Update] Repository {repo_path} status changed to {new_status}")
            except Exception as e:
                print(f"[Status Update] Failed to update priority.json: {e}")

    def cache_session_context(self, repo_path: str, result: SessionResult):
        """Caches the session context for a repository when it yields control."""
        if not repo_path:
            return
        try:
            cache_data = {
                "agent_id": result.agent_id,
                "session_id": result.session_id,
                "outcome": result.outcome,
                "snapshot_hash": result.snapshot_hash,
                "regression_context": result.regression_context,
                "next_agent_id": result.next_agent_id,
                "status_update": result.status_update,
                "timestamp": datetime.now().isoformat()
            }
            sm = StateManager(repo_path)
            sm.write_json(".exegol/session_cache.json", cache_data)
            print(f"[Orchestrator] Cached session context for {repo_path} to session_cache.json")
        except Exception as e:
            print(f"[Orchestrator] Failed to cache session context for {repo_path}: {e}")

    def load_cached_session_context(self, repo_path: str) -> Dict[str, Any]:
        """Loads the cached session context for a repository if it exists."""
        if not repo_path:
            return {}
        try:
            sm = StateManager(repo_path)
            cache = sm.read_json(".exegol/session_cache.json")
            if isinstance(cache, dict):
                return cache
        except Exception as e:
            print(f"[Orchestrator] Failed to load cached session context for {repo_path}: {e}")
        return {}

    def _write_fleet_state(self, repo_path: str, status: str, active_agent: str = None,
                           session_id: str = "", handoff_chain: List[str] = None,
                           next_agent_id: str = "", errors: List[str] = None,
                           output_summary: str = "", status_detail: str = ""):
        """Writes a truthful repo-level state even when no agent session owns the failure."""
        if not repo_path:
            return

        try:
            sm = StateManager(repo_path)
            existing = sm.read_fleet_state()
            if existing.get("status") == "blocked" and status != "blocked":
                print(f"[Status Update] Preserving blocked fleet state for {repo_path}; clear the blocker before retrying.")
                return

            state_data = {
                "active_repo": repo_path,
                "active_agent": active_agent,
                "session_id": session_id or existing.get("session_id", ""),
                "status": status,
                "started_at": datetime.now().isoformat(),
                "handoff_chain": handoff_chain or [],
                "next_agent_id": next_agent_id,
                "monologue": existing.get("monologue", []),
                "errors": errors or [],
                "output_summary": output_summary,
                "retry_available": status == "blocked",
                "failure_logged_at": datetime.now().isoformat() if status == "blocked" else "",
            }
            if status_detail:
                state_data["status_detail"] = status_detail
            sm.write_fleet_state(state_data)
        except Exception as e:
            print(f"[Status Update] Failed to write fleet_state.json: {e}")

    def _blocked_fleet_state(self, repo_path: str) -> Dict[str, Any]:
        if not repo_path:
            return {}
        try:
            state = StateManager(repo_path).read_fleet_state()
        except Exception as e:
            print(f"[Status Update] Failed to read fleet_state.json for block check: {e}")
            return {}
        return state if state.get("status") == "blocked" else {}

    def _skip_blocked_repo(self, repo_path: str) -> bool:
        state = self._blocked_fleet_state(repo_path)
        if not state:
            return False
        if self._attempt_auto_failure_recovery(repo_path, state):
            return False
        print(f"[Orchestrator] Repository {repo_path} is blocked: {state.get('output_summary', 'Fleet state is blocked.')}")
        self.update_repo_status(repo_path, "blocked")
        return True

    def _attempt_auto_failure_recovery(self, repo_path: str, state: Dict[str, Any]) -> bool:
        """Let the fleet take one self-healing pass at agent crash backlog items."""
        backlog_item_id = str(state.get("backlog_item_id") or "")
        if not state.get("retry_available") or not backlog_item_id.startswith("auto_fail_"):
            return False

        try:
            from tools.backlog_manager import BacklogManager

            bm = BacklogManager(repo_path)
            task = bm.get_task(backlog_item_id)
            if not task or task.get("status") in {"done", "completed", "archived", "dismissed"}:
                return False

            try:
                attempts = int(task.get("auto_recovery_attempts") or 0)
            except (TypeError, ValueError):
                attempts = 0

            max_attempts = int(self._get_isolation_setting("max_auto_failure_recovery_attempts", 1))
            if attempts >= max_attempts:
                return False

            now = datetime.now().isoformat()
            bm.update_task(backlog_item_id, {
                "status": "todo",
                "priority": "critical",
                "blocker_type": task.get("blocker_type") or "agent_crash",
                "recovery_agent_id": task.get("recovery_agent_id") or "developer_dex",
                "auto_recovery_attempts": attempts + 1,
                "auto_recovery_started_at": now,
            })

            StateManager(repo_path).update_fleet_state({
                "active_agent": None,
                "session_id": "",
                "status": "idle",
                "next_agent_id": "",
                "errors": [],
                "output_summary": f"Auto-recovery queued for {backlog_item_id}.",
                "retry_available": False,
                "last_cleared_errors": state.get("errors", []),
                "auto_recovery": {
                    "backlog_item_id": backlog_item_id,
                    "attempt": attempts + 1,
                    "started_at": now,
                },
            })
            self.update_repo_status(repo_path, "idle")
            print(f"[Orchestrator] Auto-recovery queued for {backlog_item_id}; continuing fleet dispatch.")
            return True
        except Exception as exc:
            print(f"[Orchestrator] Failed to prepare auto-recovery for {backlog_item_id}: {exc}")
            return False

    def _record_repo_failure(self, repo_info: Dict[str, Any], message: str,
                             errors: List[str] = None, handoff_chain: List[str] = None):
        repo_path = repo_info.get("repo_path", "")
        error_list = errors or [message]
        self.update_repo_status(repo_path, "blocked")
        self._write_fleet_state(
            repo_path=repo_path,
            status="blocked",
            active_agent="orchestrator",
            handoff_chain=handoff_chain or [],
            errors=error_list,
            output_summary=message,
        )
        log_interaction(
            agent_id="orchestrator",
            outcome="failure",
            task_summary=message,
            repo_path=repo_path,
            errors=error_list,
            state_changes={"handoff_chain": handoff_chain or []},
        )

    def retry_blocked_repo(self, repo_path: str) -> bool:
        """Move a blocked repository back to idle so the next fleet cycle can retry it."""
        self.load_config()
        sm = StateManager(repo_path)
        state_data = {}
        state_blocked = False
        try:
            state_data = sm.read_fleet_state()
            state_blocked = state_data.get("status") == "blocked"
        except Exception as e:
            print(f"[Status Update] Failed to read fleet_state.json for retry: {e}")

        for repo in self.priority_config.get("repositories", []):
            if repo.get("repo_path") == repo_path:
                if repo.get("agent_status") != "blocked" and not state_blocked:
                    return False
                if repo.get("agent_status") == "blocked":
                    self.update_repo_status(repo_path, "idle")
                self.load_config()
                self.active_target = self.get_highest_priority_task()
                if state_data:
                    try:
                        previous_errors = state_data.get("errors", [])
                        self._clear_stale_heartbeat(repo_path, state_data.get("session_id", ""))
                        state_data["status"] = "idle"
                        state_data["active_agent"] = None
                        state_data["session_id"] = ""
                        state_data["handoff_chain"] = []
                        state_data["next_agent_id"] = ""
                        state_data["errors"] = []
                        state_data["retry_available"] = False
                        state_data["output_summary"] = "Blocked state cleared for retry."
                        if previous_errors:
                            state_data["last_cleared_errors"] = previous_errors
                        sm.write_fleet_state(state_data)
                    except Exception as e:
                        print(f"[Status Update] Failed to update fleet_state.json for retry: {e}")
                return True
        return False

    def _clear_stale_heartbeat(self, repo_path: str, session_id: str) -> None:
        """Mark stale heartbeat records as cleared so supervisor polling does not re-block them."""
        heartbeat_dir = os.path.join(repo_path, ".exegol", "heartbeats")
        if not os.path.isdir(heartbeat_dir):
            return

        candidate_paths = []
        if session_id:
            candidate_paths.append(os.path.join(heartbeat_dir, f"{session_id}.json"))
        for filename in os.listdir(heartbeat_dir):
            if filename.endswith(".json"):
                path = os.path.join(heartbeat_dir, filename)
                if path not in candidate_paths:
                    candidate_paths.append(path)

        for heartbeat_path in candidate_paths:
            if not os.path.exists(heartbeat_path):
                continue
            try:
                with open(heartbeat_path, "r", encoding="utf-8") as f:
                    heartbeat = json.load(f)
                if heartbeat.get("status") in {"active", "zombie", "stale"}:
                    heartbeat["status"] = "cleared"
                    heartbeat["cleared_at"] = datetime.now().isoformat()
                    heartbeat["clear_reason"] = "Cleared from Workbench retry control."
                    with open(heartbeat_path, "w", encoding="utf-8") as f:
                        json.dump(heartbeat, f, indent=2)
            except Exception as e:
                print(f"[Status Update] Failed to clear heartbeat {os.path.basename(heartbeat_path)}: {e}")

    def _get_isolation_setting(self, key: str, default=None):
        """Read a context_isolation setting from global_settings."""
        global_settings = self.priority_config.get("global_settings", {})
        isolation = global_settings.get("context_isolation", {})
        return isolation.get(key, default)

    def get_highest_priority_task(self):
        """Determines the repo task with the highest priority score."""
        repos = self.priority_config.get("repositories", [])
        if not repos:
            return None
        
        # Sort by priority where lower number = higher priority
        sorted_repos = sorted(repos, key=lambda x: x.get('priority', 999))
        return sorted_repos[0]

    def _watch_config_loop(self):
        last_mtime = 0
        if os.path.exists(PRIORITY_FILE_PATH):
            last_mtime = os.path.getmtime(PRIORITY_FILE_PATH)
            
        while True:
            time.sleep(1)
            if os.path.exists(PRIORITY_FILE_PATH):
                current_mtime = os.path.getmtime(PRIORITY_FILE_PATH)
                if current_mtime > last_mtime:
                    last_mtime = current_mtime
                    print("\n[Event Watcher] priority.json changed. Re-evaluating 'Active' target...")
                    self.load_config()
                    self.active_target = self.get_highest_priority_task()
                    if self.active_target:
                        print(f"[Event Watcher] New 'Active' target: {self.active_target.get('repo_path')} (Priority: {self.active_target.get('priority')})")
                    else:
                        print("[Event Watcher] No actionable targets found.")

    def _watch_exegol_state_loop(self):
        """Daemon that monitors .exegol directories for state changes and triggers fleet cycle."""
        last_mtimes = {}
        while not self._should_stop_scheduler:
            time.sleep(2)
            
            # Skip checking if a fleet cycle is already actively running
            if self.is_running_fleet:
                continue
                
            repos = self.priority_config.get("repositories", [])
            active_repos = [r for r in repos if r.get('agent_status', 'idle') in ['active', 'idle']]
            
            fleet_triggered = False
            for repo in active_repos:
                if is_runtime_stopped():
                    fleet_triggered = False
                    break
                repo_path = repo.get("repo_path")
                if not repo_path:
                    continue
                
                exegol_dir = os.path.join(repo_path, ".exegol")
                if not os.path.exists(exegol_dir):
                    continue
                
                # Check critical state files for new tasks or state changes
                for filename in ["backlog.json", "user_action_required.json"]:
                    file_path = os.path.join(exegol_dir, filename)
                    if os.path.exists(file_path):
                        current_mtime = os.path.getmtime(file_path)
                        
                        if file_path not in last_mtimes:
                            last_mtimes[file_path] = current_mtime
                        elif current_mtime > last_mtimes[file_path]:
                            last_mtimes[file_path] = current_mtime
                            print(f"\n[Exegol Daemon] State change detected in {filename} for {repo_path}")
                            fleet_triggered = True
                            
            if fleet_triggered:
                print("[Exegol Daemon] Automatically triggering fleet cycle...")
                # Run fleet cycle asynchronously to prevent blocking the daemon
                threading.Thread(target=self.run_fleet_cycle, daemon=True).start()


    def start_event_listener(self):
        """Starts the event listener threads to watch for config and state changes."""
        listener_thread = threading.Thread(target=self._watch_config_loop, daemon=True)
        listener_thread.start()
        
        exegol_watcher_thread = threading.Thread(target=self._watch_exegol_state_loop, daemon=True)
        exegol_watcher_thread.start()
        
        print("Event listeners started. Watching priority.json and .exegol directories for updates.")

    def run_fleet_cycle(
        self,
        repo_path: Optional[str] = None,
        include_due_scheduled: bool = False,
        trigger_source: str = "manual_run",
    ):
        """Runs one full cycle through the fleet, or a selected repo when provided."""
        if not hasattr(self, "_fleet_cycle_lock"):
            self._fleet_cycle_lock = threading.Lock()
        if not self._fleet_cycle_lock.acquire(blocking=False):
            print("[Orchestrator] Fleet cycle already running. Skipping overlapping request.")
            return False

        print("\nStarting Fleet Cycle...")
        resume_runtime("fleet cycle starting")
        self.clear_fleet_stop_request()
        self.is_running_fleet = True
        all_success = True
        try:
            defer_scheduled = bool(repo_path) and self._should_defer_scheduled_for_zero_to_one(repo_path)
            if include_due_scheduled and defer_scheduled:
                print("[Scheduler] Skipping due scheduled jobs until zero-to-one onboarding completes.")
            elif include_due_scheduled:
                due_result = self.run_due_scheduled_agents(
                    repo_path=repo_path,
                    trigger_source=trigger_source,
                )
                if due_result.get("triggered_count", 0):
                    print(f"[Scheduler] Ran {due_result['triggered_count']} due scheduled job(s) before fleet dispatch.")

            # Periodic Audits
            self.check_compliance_monitoring()

            if repo_path:
                sorted_repos = [self._repo_info_for_path(repo_path)]
            else:
                repos = self.priority_config.get("repositories", [])
                active_repos = [r for r in repos if r.get('agent_status', 'idle') in ['active', 'idle']]
                sorted_repos = sorted(active_repos, key=lambda x: x.get('priority', 999))
            
            for repo_info in sorted_repos:
                if self.is_fleet_stop_requested() or not self.is_running_fleet:
                    all_success = False
                    break
                repo_path = repo_info.get("repo_path", "")
                if self._skip_blocked_repo(repo_path):
                    all_success = False
                    continue
                self._write_fleet_state(
                    repo_path=repo_path,
                    status="running",
                    active_agent="orchestrator",
                    output_summary="Fleet cycle is evaluating this repository.",
                )
                try:
                    self.process_repo(repo_info)
                    if self.is_fleet_stop_requested() or not self.is_running_fleet:
                        all_success = False
                        print("[Orchestrator] Fleet cycle stopped before further dispatch.")
                        break

                    # Check if the repository status has become 'idle' or 'blocked'
                    self.load_config()
                    updated_repo = self._repo_info_for_path(repo_path)
                    status = updated_repo.get("agent_status", "idle")
                    if status in ["idle", "blocked"]:
                        print(f"[Orchestrator] Repository {repo_path} status became '{status}'. Yielding control to next priority repo.")
                        continue
                except Exception as e:
                    all_success = False
                    message = f"Fleet cycle failed while processing repository: {type(e).__name__}: {e}"
                    print(f"[Orchestrator] {message}")
                    self._record_repo_failure(
                        repo_info,
                        message,
                        errors=traceback.format_exception_only(type(e), e),
                    )
            
            print("Fleet Cycle complete.")
            return all_success
        finally:
            self.is_running_fleet = False
            self.clear_fleet_stop_request()
            self._fleet_cycle_lock.release()


    def _repo_info_for_path(self, repo_path: str) -> Dict[str, Any]:
        """Return configured repo metadata for a path, falling back to a runnable target."""
        normalized = os.path.abspath(repo_path)
        for repo in self.priority_config.get("repositories", []):
            configured = repo.get("repo_path", "")
            if os.path.abspath(configured) == normalized:
                repo_info = dict(repo)
                repo_info["repo_path"] = normalized
                return repo_info
        return {
            "repo_path": normalized,
            "priority": 1,
            "agent_status": "active",
            "model_routing_preference": os.getenv("LLM_PROVIDER", "ollama"),
        }

    def _should_defer_scheduled_for_zero_to_one(self, repo_path: str) -> bool:
        try:
            onboarding = zero_to_one_status(repo_path)
            if onboarding.get("action") in {"kickoff", "wait", "activate"}:
                return True
            objective = ObjectiveManager(repo_path).load()
            has_active_objective = bool(str(objective.get("goal") or "").strip())
            phase = str(objective.get("phase") or "").lower()
            objective_status = str(objective.get("status") or "").lower()
            if has_active_objective and phase != "done" and objective_status in {"running", "paused"}:
                return True
            return is_zero_to_one_repo(repo_path) and has_active_objective and phase != "done"
        except Exception as exc:
            print(f"[Onboarding] Failed to inspect zero-to-one status before scheduled jobs: {exc}")
            return False

    def process_repo(self, repo_info: Dict[str, Any]):
        """Decides which agent to wake for a given repo based on its current state."""
        repo_path = repo_info.get("repo_path")
        print(f"\nChecking repo: {repo_path}")
        if self.is_fleet_stop_requested():
            self._write_fleet_state(
                repo_path=repo_path,
                status="idle",
                active_agent=None,
                output_summary="Fleet stop requested before agent dispatch.",
            )
            return
        if self._skip_blocked_repo(repo_path):
            return
        
        # Check if .exegol exists, otherwise trigger Thrawn (onboarding)
        exegol_dir = os.path.join(repo_path, ".exegol")
        if not os.path.exists(exegol_dir):
            if self._should_defer_scheduled_for_zero_to_one(repo_path):
                self._start_zero_to_one_onboarding(repo_info)
                return

            print(f"[Onboarding] No .exegol found. Triggering ThoughtfulThrawnAgent...")
            self.wake_and_execute_agent(repo_info, repo_info.get('model_routing_preference', 'ollama'), 5, "thoughtful_thrawn")
            return

        onboarding = zero_to_one_status(repo_path)
        if onboarding.get("action") == "kickoff":
            self._start_zero_to_one_onboarding(repo_info)
            return
        if onboarding.get("action") == "wait":
            pending = onboarding.get("pending_onboarding", [])
            active_agent = "vibe_vader" if any("Vader:" in str(item.get("task", "")) for item in pending) else "thoughtful_thrawn"
            self._write_fleet_state(
                repo_path=repo_path,
                status="awaiting_human",
                active_agent=active_agent,
                output_summary=onboarding.get("summary", "Waiting for human onboarding input."),
                status_detail="Resolve the Thrawn/Vader onboarding prompts before autonomous coding starts.",
            )
            return
        if onboarding.get("action") == "activate":
            objective = activate_zero_to_one_objective(repo_path)
            if objective:
                print(f"[Onboarding] Activated zero-to-one objective: {objective.get('goal')}")
            else:
                self._write_fleet_state(
                    repo_path=repo_path,
                    status="awaiting_human",
                    active_agent="thoughtful_thrawn",
                    output_summary="Waiting for a usable objective before autonomous coding starts.",
                    status_detail="Answer Thrawn's primary objective prompt or set the objective directly.",
                )
                return

        if self._dispatch_objective_step(repo_info):
            return

        # Check backlog for pending tasks (including prioritized 'todo' tasks)
        from tools.backlog_manager import BacklogManager
        backlog = BacklogManager(repo_path).load_backlog()
        pending_tasks = [t for t in backlog if t.get("status") in ["pending_prioritization", "backlogged", "todo"]]
        if pending_tasks:
            print(f"Found {len(pending_tasks)} pending/todo tasks. Triggering ProductPoeAgent...")
            self.wake_and_execute_agent(repo_info, repo_info.get('model_routing_preference', 'ollama'), 10, "product_poe")
            return

        # If it's a Monday or specific time, run review/optimizer (Logic TBD)
        print("Repo is idle.")
        self._write_fleet_state(
            repo_path=repo_path,
            status="idle",
            output_summary="No pending autonomous work found.",
        )

    def _start_zero_to_one_onboarding(self, repo_info: Dict[str, Any]) -> None:
        repo_path = repo_info.get("repo_path", "")
        routing = repo_info.get("model_routing_preference", "ollama")
        print("[Onboarding] Empty repository needs zero-to-one intent capture. Triggering Thrawn and Vader...")

        thrawn_result = self.wake_and_execute_agent(
            repo_info,
            routing,
            5,
            "thoughtful_thrawn",
            allow_chaining=False,
        )
        if thrawn_result and getattr(thrawn_result, "outcome", "") == "failure":
            return

        if not self.is_fleet_stop_requested():
            self.wake_and_execute_agent(
                repo_info,
                routing,
                10,
                "vibe_vader",
                allow_chaining=False,
            )

        onboarding = zero_to_one_status(repo_path)
        self._write_fleet_state(
            repo_path=repo_path,
            status="awaiting_human",
            active_agent="thoughtful_thrawn",
            output_summary=onboarding.get(
                "summary",
                "Waiting for human onboarding input before autonomous coding.",
            ),
            status_detail="Resolve the Thrawn/Vader onboarding prompts before autonomous coding starts.",
        )

    def _dispatch_objective_step(self, repo_info: Dict[str, Any]) -> bool:
        """Route active objective phases before falling back to generic backlog work."""
        repo_path = repo_info.get("repo_path")
        manager = ObjectiveManager(repo_path)
        objective = manager.load()
        goal = str(objective.get("goal") or "").strip()
        if not goal:
            return False

        status = objective.get("status", "idle")
        if status == "paused":
            self._write_fleet_state(
                repo_path=repo_path,
                status="paused",
                active_agent=None,
                output_summary="Objective execution is paused.",
            )
            return True

        phase = objective.get("phase", "idle")
        if phase in {"done", "failed_budget", "blocked_human"}:
            self._write_fleet_state(
                repo_path=repo_path,
                status=objective.get("status", "idle"),
                active_agent=None,
                output_summary=self._objective_status_summary(objective),
            )
            return True

        if phase == "blocked_environment":
            if manager.can_transition("remediating"):
                objective = manager.transition("remediating", last_agent_id="orchestrator")
                phase = objective["phase"]

        if phase == "idle":
            objective = manager.transition("planning", last_agent_id="orchestrator")
            phase = objective["phase"]

        dispatch = self._objective_dispatch_for_phase(phase)
        if not dispatch:
            return False

        agent_id, max_steps = dispatch
        self._write_fleet_state(
            repo_path=repo_path,
            status="running",
            active_agent=agent_id,
            output_summary=f"Objective phase '{phase}' dispatched to {agent_id}.",
        )
        result = self.wake_and_execute_agent(
            repo_info,
            repo_info.get("model_routing_preference", "ollama"),
            max_steps,
            agent_id,
            allow_chaining=False,
        )
        self._record_objective_result(manager, phase, agent_id, result)
        return True

    @staticmethod
    def _objective_dispatch_for_phase(phase: str) -> Optional[tuple[str, int]]:
        dispatch = {
            "planning": ("product_poe", 10),
            "implementing": ("developer_dex", 15),
            "validating": ("quality_quigon", 10),
            "accepting": ("uat_ulic", 10),
            "retrying": ("developer_dex", 10),
            "remediating": ("watcher_wedge", 10),
        }
        return dispatch.get(phase)

    def _record_objective_result(self, manager: ObjectiveManager, phase: str, agent_id: str, result: Any) -> None:
        result_summary = self._objective_result_payload(result)
        if not result:
            self._safe_objective_transition(
                manager,
                "blocked_environment",
                last_agent_id=agent_id,
                last_result=result_summary,
                blocked_reason=f"{agent_id} did not return a result.",
            )
            return

        outcome = getattr(result, "outcome", "unknown")
        if outcome == "success":
            next_phase = {
                "planning": "implementing",
                "implementing": "validating",
                "validating": "accepting",
                "accepting": "done",
                "retrying": "implementing",
                "remediating": "retrying",
            }.get(phase)
            if next_phase:
                self._safe_objective_transition(
                    manager,
                    next_phase,
                    last_agent_id=getattr(result, "agent_id", agent_id),
                    last_result=result_summary,
                )
            return

        blocked_reason = "; ".join(getattr(result, "errors", []) or []) or getattr(result, "output_summary", "") or f"{agent_id} failed."
        next_phase = "retrying" if phase in {"implementing", "validating", "accepting"} else "blocked_environment"
        self._safe_objective_transition(
            manager,
            next_phase,
            last_agent_id=getattr(result, "agent_id", agent_id),
            last_result=result_summary,
            blocked_reason=blocked_reason if next_phase == "blocked_environment" else None,
        )
        if next_phase == "retrying":
            self.update_repo_status(manager.repo_path, "idle")
            self._write_fleet_state(
                repo_path=manager.repo_path,
                status="running",
                active_agent=None,
                output_summary=f"Objective validation failed in phase '{phase}'. Retrying with developer_dex.",
            )

    @staticmethod
    def _objective_result_payload(result: Any) -> Dict[str, Any]:
        if not result:
            return {"outcome": "missing_result"}
        return {
            "agent_id": getattr(result, "agent_id", None),
            "session_id": getattr(result, "session_id", None),
            "outcome": getattr(result, "outcome", None),
            "output_summary": getattr(result, "output_summary", ""),
            "errors": getattr(result, "errors", []),
            "next_agent_id": getattr(result, "next_agent_id", ""),
        }

    @staticmethod
    def _objective_status_summary(objective: Dict[str, Any]) -> str:
        goal = objective.get("goal") or "Objective"
        phase = objective.get("phase") or "unknown"
        if objective.get("blocked_reason"):
            return f"{goal} is {phase}: {objective['blocked_reason']}"
        return f"{goal} is {phase}."

    @staticmethod
    def _safe_objective_transition(manager: ObjectiveManager, phase: str, **kwargs) -> None:
        try:
            manager.transition(phase, **kwargs)
        except ValueError as exc:
            manager.transition(
                "blocked_environment",
                last_agent_id=kwargs.get("last_agent_id"),
                last_result=kwargs.get("last_result"),
                blocked_reason=str(exc),
            )

    def check_compliance_monitoring(self):
        """Checks if a monthly compliance sweep is due and triggers Cody."""
        global_settings = self.priority_config.get("global_settings", {})
        monitoring = global_settings.get("compliance_monitoring", {})
        if not monitoring:
            return

        last_run_str = monitoring.get("last_run", "1970-01-01")
        frequency_days = monitoring.get("frequency_days", 30)

        try:
            from datetime import datetime, timedelta
            last_run = datetime.fromisoformat(last_run_str)
            if datetime.now() > last_run + timedelta(days=frequency_days):
                print(f"[Compliance] Monthly sweep is due (last run: {last_run_str}). Waking ComplianceCody...")
                # Run for the primary repo (or all, but Cody searches global anyway)
                target = self.get_highest_priority_task()
                if target:
                    result = self.wake_and_execute_agent(
                        repo_info=target,
                        routing=target.get("model_routing_preference", "ollama"),
                        max_steps=15,
                        agent_id="compliance_cody"
                    )
                    if result and result.outcome == "success":
                        # Update last_run in priority.json
                        monitoring["last_run"] = datetime.now().date().isoformat()
                        self.save_config()
            else:
                print(f"[Compliance] Monthly sweep not due. Next run after: {(last_run + timedelta(days=frequency_days)).date()}")
        except Exception as e:
            print(f"[Compliance] Error checking monitoring: {e}")

    def save_config(self):
        """Saves current priority_config back to priority.json."""
        try:
            with open(PRIORITY_FILE_PATH, 'w') as f:
                json.dump(self.priority_config, f, indent=2)
            print("[Config] priority.json updated successfully.")
        except Exception as e:
            print(f"[Config] Failed to save priority.json: {e}")

    def trigger_go(self):
        """Manual 'Go' trigger for the active target."""
        if not self._fleet_cycle_lock.acquire(blocking=False):
            print("[Orchestrator] Another fleet cycle or Go run is already active. Skipping duplicate Go.")
            return False

        try:
            # --- SECURITY GUARD: CLI Auth (sec_sec_arch_001) ---
            api_key = os.getenv("EXEGOL_API_KEY")
            if api_key:
                 # In a real CLI, we might prompt for a key or check a local token
                 # For now, we just log that we are running in authenticated mode
                 print("[Orchestrator] Running 'Go' in authenticated CLI mode.")

            print("Received 'Go' trigger. Initiating orchestration cycle...")
            target_repo = self.active_target
            if not target_repo:
                print("No actionable repositories found.")
                return False

            repo_path = target_repo.get("repo_path", "")
            if self._skip_blocked_repo(repo_path):
                return False
            self._write_fleet_state(
                repo_path=repo_path,
                status="running",
                active_agent="orchestrator",
                output_summary="Manual Go is evaluating this repository.",
            )
            try:
                self.process_repo(target_repo)
                return True
            except Exception as e:
                message = f"Manual Go failed while processing repository: {type(e).__name__}: {e}"
                print(f"[Orchestrator] {message}")
                self._record_repo_failure(
                    target_repo,
                    message,
                    errors=traceback.format_exception_only(type(e), e),
                )
                return False
        finally:
            self._fleet_cycle_lock.release()

    def wake_and_execute_agent(self, repo_info: Dict[str, Any], routing: str, max_steps: int,
                                agent_id: str = None, snapshot_hash: str = "", regression_context: str = "",
                                loop_depth: int = 0, chain_history: List[str] = None, scheduled_prompt: str = "",
                                allow_chaining: bool = True):
        if agent_id is None:
            agent_id = "product_poe"

        path = repo_info.get("repo_path")
        if not snapshot_hash or not regression_context:
            cache = self.load_cached_session_context(path)
            if cache:
                if not snapshot_hash:
                    snapshot_hash = cache.get("snapshot_hash", "")
                if not regression_context:
                    regression_context = cache.get("regression_context", "")

        stop_requested_before_wake = self.is_fleet_stop_requested()
        acquired = self.acquire_execution_lock(agent_id)
        if not acquired:
            return SessionResult(
                agent_id=agent_id,
                session_id="cancelled",
                outcome="cancelled",
                status_update="idle",
                output_summary="Fleet stop requested before agent execution lock was acquired.",
            )
        result = None
        try:
            result = self._wake_and_execute_agent_inner(
                repo_info, routing, max_steps, agent_id, snapshot_hash, regression_context,
                loop_depth, chain_history, scheduled_prompt, allow_chaining
            )
        finally:
            self.release_execution_lock()

        if (
            result
            and self.is_fleet_stop_requested()
            and (self.is_running_fleet or not stop_requested_before_wake)
            and getattr(result, "outcome", "") == "success"
        ):
            print("[Orchestrator] Fleet stop requested; suppressing autonomous handoff.")
            result.next_agent_id = ""
            result.status_update = getattr(result, "status_update", "") or "idle"
            
        if result:
            status = getattr(result, "status_update", "")
            if not status:
                if result.outcome == "failure":
                    status = "blocked"
                elif not getattr(result, "next_agent_id", ""):
                    status = "idle"

            # Cache the current session context
            self.cache_session_context(path, result)

            # Update repo status in priority.json if status is set
            if status:
                self.update_repo_status(path, status)

            # Yield control immediately if status becomes idle or blocked (do not chain further)
            if status in ["idle", "blocked"]:
                print(f"[Orchestrator] Agent status became '{status}'. Yielding control for {path}.")
                return result

        if result and getattr(result, "next_agent_id", None) and result.outcome == "success":
            if not allow_chaining:
                print(f"[Orchestrator] Chaining disabled. Returning current agent result without handoff to {result.next_agent_id}")
                return result

            print(f"[Orchestrator] Autonomous handoff requested: {agent_id} -> {result.next_agent_id}")
            registry_entry = AGENT_REGISTRY.get(result.next_agent_id)
            if registry_entry:
                # Small delay to ensure logs are flushed and system is ready
                time.sleep(1)
                
                # Update history here since we moved it out of the inner loop's recursion
                current_depth = loop_depth + 1
                current_history = (chain_history or []) + [agent_id]
                
                return self.wake_and_execute_agent(
                    repo_info=repo_info,
                    routing=routing,
                    max_steps=registry_entry.get("max_steps", 15),
                    agent_id=result.next_agent_id,
                    snapshot_hash=getattr(result, "snapshot_hash", ""),
                    regression_context=getattr(result, "regression_context", ""),
                    loop_depth=current_depth,
                    chain_history=current_history,
                    allow_chaining=allow_chaining
                )
            else:
                print(f"[Orchestrator] Error: Requested next agent '{result.next_agent_id}' not found in registry.")

        return result

    def _wake_and_execute_agent_inner(self, repo_info: Dict[str, Any], routing: str, max_steps: int,
                                agent_id: str = None, snapshot_hash: str = "", regression_context: str = "",
                                loop_depth: int = 0, chain_history: List[str] = None, scheduled_prompt: str = "",
                                allow_chaining: bool = True):
        """Dispatch an agent through SessionManager for a fully isolated session."""
        if agent_id is None:
            agent_id = "product_poe"
        
        if chain_history is None:
            chain_history = []

        # --- SECURITY GUARD: Agent-Trigger RBAC (sec_sec_arch_001) ---
        if chain_history:
            caller_id = chain_history[-1]
            from tools.rbac_manager import RBACManager
            # Check if caller has permission to trigger agents
            if not RBACManager.check_permission(caller_id, "agent:trigger"):
                msg = f"SECURITY: Agent '{caller_id}' REJECTED from triggering '{agent_id}'. Missing 'agent:trigger' permission."
                print(f"[Orchestrator] {msg}")
                return None        
        # 1. Loop Guard: Check max depth
        max_depth = self._get_isolation_setting("max_handoff_depth", 8)
        if loop_depth >= max_depth:
            msg = f"[Orchestrator] CRITICAL: Max loop depth ({max_depth}) reached for chain: {' -> '.join(chain_history)}"
            print(msg)
            slack_manager.post_message(f"🚨 *Loop Guard Triggered*: {msg}")
            
            log_interaction(
                agent_id="orchestrator",
                outcome="failure",
                task_summary="Loop depth guard triggered.",
                repo_path=repo_info.get("repo_path", ""),
                errors=[msg],
                state_changes={"chain_history": chain_history}
            )
            
            self.update_repo_status(repo_info.get("repo_path"), "blocked")
            self._write_fleet_state(
                repo_path=repo_info.get("repo_path", ""),
                status="blocked",
                active_agent="orchestrator",
                handoff_chain=chain_history,
                errors=[msg],
                output_summary="Loop depth guard triggered.",
            )
            self.escalate_to_human(msg, repo_info.get("repo_path"))
            return None

        # 2. Circuit Breaker: Detect simple cycles (A -> B -> A) or repeated agents
        if agent_id in chain_history:
            # If the same agent appears more than twice, or if it's a tight loop
            occurrences = chain_history.count(agent_id)
            if occurrences >= 2:
                msg = f"[Orchestrator] CIRCUIT BREAKER: Cycle detected. Agent '{agent_id}' already appeared twice in {chain_history}"
                print(msg)
                slack_manager.post_message(f"🔒 *Circuit Breaker Triggered*: {msg}")
                
                log_interaction(
                    agent_id="orchestrator",
                    outcome="failure",
                    task_summary="Circuit breaker triggered (cycle detected).",
                    repo_path=repo_info.get("repo_path", ""),
                    errors=[msg],
                    state_changes={"chain_history": chain_history, "offending_agent": agent_id}
                )
                
                self.update_repo_status(repo_info.get("repo_path"), "blocked")
                self._write_fleet_state(
                    repo_path=repo_info.get("repo_path", ""),
                    status="blocked",
                    active_agent="orchestrator",
                    handoff_chain=chain_history,
                    errors=[msg],
                    output_summary="Circuit breaker triggered.",
                )
                self.escalate_to_human(msg, repo_info.get("repo_path"))
                return None

        # Update history for the current run
        current_history = chain_history + [agent_id]
        current_depth = loop_depth + 1

        # Check for dynamic model override in config/agent_models.json
        agent_models_path = os.path.join(os.path.dirname(PRIORITY_FILE_PATH), 'agent_models.json')
        if os.path.exists(agent_models_path):
            try:
                with open(agent_models_path, 'r') as f:
                    agent_models = json.load(f)
                if agent_id in agent_models:
                    routing = agent_models[agent_id]
            except Exception as e:
                print(f"[Orchestrator] Error reading config/agent_models.json: {e}")

        registry_entry = AGENT_REGISTRY.get(agent_id)
        if not registry_entry:
            print(f"Unknown agent: {agent_id}")
            return

        # Standardize execution limits to a uniform repository limit (configured to 30) rather than repository-specific
        standardized_limit = repo_info.get("max_steps_policy", 30)
        actual_max_steps = min(standardized_limit, registry_entry.get("max_steps", 50))

        handoff = HandoffContext(
            repo_path=repo_info.get("repo_path", ""),
            agent_id=agent_id,
            task_id="fleet_cycle" if self.is_running_fleet else "manual_go",
            model_routing=routing,
            max_steps=actual_max_steps,
            snapshot_hash=snapshot_hash,
            regression_context=regression_context,
            loop_depth=current_depth,
            chain_history=current_history,
            scheduled_prompt=scheduled_prompt
        )
        
        # --- SECURITY GUARD: Sign Handoff (sec_sec_arch_005) ---
        signed_handoff = self._sign_handoff(handoff)
        
        result = self.session_manager.spawn_agent_session(
            agent_id=agent_id,
            module_path=registry_entry["module"],
            class_name=registry_entry["class"],
            handoff=signed_handoff,
        )
        
        return result

    def _sign_handoff(self, handoff: HandoffContext) -> HandoffContext:
        """Computes and attaches an HMAC signature to the HandoffContext."""
        secret = os.getenv("EXEGOL_HMAC_SECRET", "dev-secret-keep-it-safe")
        
        data = f"{handoff.repo_path}|{handoff.agent_id}|{handoff.session_id}|{handoff.timestamp}"
        
        signature = hmac.new(
            secret.encode(),
            data.encode(),
            hashlib.sha256
        ).hexdigest()
        
        # frozen=True dataclass needs object.__setattr__
        object.__setattr__(handoff, "signature", signature)
        return handoff

    def escalate_to_human(self, message: str, repo_path: str):
        """Escalates a critical autonomous failure to the human-in-the-loop queue."""
        sm = StateManager(repo_path)
        
        # Generate a stable ID for the loop guard failure
        task_id = f"loop_guard_{hashlib.md5(message.encode()).hexdigest()[:8]}"
        
        # Use the standardized escalation method
        sm.add_hitl_task(
            summary=f"BLOCKING ISSUE: {message}",
            category="infrastructure",
            context="Orchestrator loop guard or depth limit reached.",
            task_id=task_id
        )
        
        print(f"[Orchestrator] Escalated to human: {message}")

    def display_help(self, channel: str = None):
        """Displays a rich help message in Slack with available commands and agents."""
        blocks = [
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": "👋 *Exegol V3 Orchestrator Help*\nI'm listening for several commands and agent wake-words. Here's what I can do:"
                }
            },
            {
                "type": "divider"
            },
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": "*Global Fleet Commands:*\n"
                            "• `go` — Triggers the highest priority task on the active repository.\n"
                            "• `fleet` — Initiates a full cycle through all active repositories.\n"
                            "• `backlog <task>` — Adds a task directly to the active repo's backlog.\n"
                            "• `stop` — Gracefully shuts down the orchestrator.\n"
                            "• `help` / `info` — Shows this message."
                }
            },
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": "*Available Agents (Who is listening):*\n"
                            "Wake an agent by name followed by your request (e.g., `dex fix the bug`)."
                }
            }
        ]

        # Add agent info (chunked if too many)
        agent_fields = []
        for agent_id, details in AGENT_REGISTRY.items():
            wake_word = details["wake_word"]
            tools = ", ".join(details["tools"][:3])
            agent_fields.append({
                "type": "mrkdwn",
                "text": f"*{agent_id}* (`{wake_word}`)\n_{tools}_"
            })
            
            # Slack sections allow max 10 fields
            if len(agent_fields) >= 10:
                blocks.append({"type": "section", "fields": agent_fields})
                agent_fields = []
        
        if agent_fields:
            blocks.append({"type": "section", "fields": agent_fields})

        blocks.append({
            "type": "context",
            "elements": [
                {
                    "type": "mrkdwn",
                    "text": "💡 *Tip*: Use `poe: <idea>` to have Poe groom your request into a proper backlog item."
                }
            ]
        })

        slack_manager.post_message("Exegol Help", blocks=blocks, channel=channel)

    def handle_wake_word(self, command_string: str, channel: str = None):
        """Processes CLI/Slack input to trigger specific agents or default 'go' behavior."""
        cmd = command_string.lower()

        if "help" in cmd or "info" in cmd:
            self.display_help(channel=channel)
            return

        if "fleet" in cmd:
            slack_manager.post_message("🚀 Fleet cycle starting — processing all active repos...", channel=channel)
            self.run_fleet_cycle()
            slack_manager.post_message("✅ Fleet cycle complete.", channel=channel)
            return

        if cmd.startswith("add to backlog") or cmd.startswith("backlog"):
            from tools.backlog_manager import BacklogManager
            import uuid
            import datetime
            
            prefix = "add to backlog" if cmd.startswith("add to backlog") else "backlog"
            content = command_string[cmd.find(prefix) + len(prefix):].strip()
            if content.startswith(":"):
                content = content[1:].strip()
                
            if not content:
                slack_manager.post_message("❌ Please provide a task description. Example: `backlog review PRs`", channel=channel)
                return

            target = self.active_target or {"repo_path": os.path.dirname(os.path.dirname(__file__))}
            repo_path = target.get("repo_path")
            
            bm = BacklogManager(repo_path)
            new_task = {
                "id": f"slack_{uuid.uuid4().hex[:6]}",
                "summary": content,
                "status": "pending_prioritization",
                "priority": "medium",
                "source": "slack",
                "created_at": datetime.datetime.now().isoformat()
            }
            if bm.add_task(new_task):
                repo_name = os.path.basename(repo_path)
                slack_manager.post_message(f"✅ Added to backlog for `{repo_name}`:\n_{content}_", channel=channel)
            else:
                slack_manager.post_message(f"⚠️ Failed to add task to backlog.", channel=channel)
            return

        for agent_id, details in AGENT_REGISTRY.items():
            wake_word = details["wake_word"]
            if wake_word in cmd:
                # Extract context after wake word
                idx = cmd.find(wake_word)
                raw_context = command_string[idx + len(wake_word):].strip()
                if raw_context.startswith(":") or raw_context.startswith("-"):
                    raw_context = raw_context[1:].strip()
                
                print(f"Triggering specific agent: {agent_id} by wake word '{wake_word}'")
                slack_manager.post_message(f"🤖 Waking `{agent_id}`... {f'Context: _{raw_context}_' if raw_context else ''}", channel=channel)
                
                target = self.active_target or {"repo_path": os.path.dirname(os.path.dirname(__file__))}
                routing = target.get("model_routing_preference", "ollama")
                self.wake_and_execute_agent(
                    repo_info=target,
                    routing=routing,
                    max_steps=details["max_steps"],
                    agent_id=agent_id,
                    scheduled_prompt=raw_context
                )
                return

        if "stop" in cmd:
            slack_manager.post_message("🛑 `stop` received — shutting down Exegol orchestrator...", channel=channel)
            print("\n[Slack] Stop command detected. Shutting down...")
            self.shutdown()
            return

        if "go" in cmd:
            slack_manager.post_message("🚀 `go` received — triggering active repository...", channel=channel)
            self.trigger_go()
            return

        print(f"Unknown command or wake word in: '{command_string}'")
        slack_manager.post_message(
            f"❓ Unknown command: `{command_string}`\nType `help` for available commands.",
            channel=channel
        )

    def shutdown(self):
        """Performs a clean shutdown of the orchestrator and its background threads."""
        print("[Shutdown] Initiating graceful shutdown...")
        self._should_stop_scheduler = True
        self.is_running_fleet = False
        self._write_scheduler_state("stopping", detail="orchestrator shutdown requested")
        
        # Stop heartbeat monitor watchdog threads
        if hasattr(self, "session_manager"):
            self.session_manager.shutdown_monitors()
        
        # Give threads a moment to catch the stop signals
        time.sleep(1)
        
        print("[Shutdown] Exiting process.")
        sys.exit(0)

if __name__ == "__main__":
    orchestrator = ExegolOrchestrator()
    
    if len(sys.argv) > 1 and sys.argv[1] == "--fleet":
        orchestrator.run_fleet_cycle()
    else:
        orchestrator.start_event_listener()
        print("\nOrchestrator is ready.")
        print("Type 'go' for active repo, 'fleet' for all repos, or a wake word (e.g. 'record').")
        
        try:
            while True:
                cmd = input("> ").strip().lower()
                if cmd in ["exit", "quit"]:
                    break
                elif cmd:
                    orchestrator.handle_wake_word(cmd)
        except KeyboardInterrupt:
            print("\nShutting down orchestrator.")
