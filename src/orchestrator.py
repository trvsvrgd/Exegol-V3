import json
import os
import time
import threading
import sys
import schedule
import hmac
import hashlib
from datetime import datetime
from dotenv import load_dotenv

# Load environment variables before any other imports
load_dotenv()

from typing import Dict, Any, List
from agents.registry import AGENT_REGISTRY
from handoff import HandoffContext
from session_manager import SessionManager
from tools.slack_tool import slack_manager
from tools.fleet_logger import log_interaction
from tools.state_manager import StateManager

PRIORITY_FILE_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'config', 'priority.json')
HISTORY_FILE_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'config', 'job_history.json')

class ExegolOrchestrator:
    def __init__(self):
        self.priority_config: Dict[str, Any] = {}
        self.load_config()
        self.active_target = self.get_highest_priority_task()
        self.session_manager = SessionManager(
            log_every_session=self._get_isolation_setting("log_every_session", True)
        )
        self.is_running_fleet = False
        self._should_stop_scheduler = False
        self.job_history = self._load_job_history()
        
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
        
        # Initialize Autonomous Cadence Engine
        self._setup_cadence_engine()

    def get_agent_priority(self, agent_id):
        try:
            return self.agent_priority_order.index(agent_id)
        except ValueError:
            return 999

    def acquire_execution_lock(self, agent_id):
        priority = self.get_agent_priority(agent_id)
        import uuid
        ticket = {"id": str(uuid.uuid4()), "priority": priority, "agent_id": agent_id}
        
        with self.queue_condition:
            self.pending_tasks.append(ticket)
            self.pending_tasks.sort(key=lambda x: x["priority"])
            while self.current_running_agent is not None or self.pending_tasks[0]["id"] != ticket["id"]:
                self.queue_condition.wait()
            self.current_running_agent = ticket
            self.pending_tasks.pop(0)

    def release_execution_lock(self):
        with self.queue_condition:
            self.current_running_agent = None
            self.queue_condition.notify_all()

    def _setup_cadence_engine(self):
        """Configures periodic autonomous tasks for the fleet from config."""
        cadence_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "config", "fleet_cadence.json")
        if not os.path.exists(cadence_path):
            print("[Scheduler] No fleet_cadence.json found. Skipping cadence engine.")
            return

        try:
            with open(cadence_path, "r", encoding="utf-8") as f:
                config = json.load(f)
            
            if not config.get("global_settings", {}).get("enable_scheduler", True):
                print("[Scheduler] Scheduler disabled in config.")
                return

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
                
                s.do(self._scheduled_trigger, agent_id=agent_id, summary=summary, job_id=job.get("id"))
                print(f"[Scheduler] Registered: {summary} ({agent_id}) @ {freq} {at_time or ''}")

            # Check for missed jobs
            self._check_for_missed_jobs(config)

            # Start Scheduler Thread
            self._check_interval = config.get("global_settings", {}).get("check_interval_seconds", 60)
            self.scheduler_thread = threading.Thread(target=self._run_scheduler, daemon=True)
            self.scheduler_thread.start()
            print(f"[Scheduler] Cadence engine started (interval: {self._check_interval}s).")

        except Exception as e:
            print(f"[Scheduler] Error setting up cadence engine: {e}")

    def _run_scheduler(self):
        while not self._should_stop_scheduler:
            schedule.run_pending()
            time.sleep(self._check_interval)

    def _load_job_history(self) -> Dict[str, str]:
        if os.path.exists(HISTORY_FILE_PATH):
            try:
                with open(HISTORY_FILE_PATH, "r", encoding="utf-8") as f:
                    return json.load(f)
            except:
                return {}
        return {}

    def _save_job_history(self):
        try:
            with open(HISTORY_FILE_PATH, "w", encoding="utf-8") as f:
                json.dump(self.job_history, f, indent=4)
        except Exception as e:
            print(f"[Scheduler] Failed to save job history: {e}")

    def _check_for_missed_jobs(self, config):
        """Checks if any jobs should have run while the fleet was down."""
        from datetime import timedelta
        now = datetime.now()
        
        for job in config.get("schedules", []):
            if not job.get("enabled", True): continue
            job_id = job.get("id")
            if not job_id: continue
            
            last_run_str = self.job_history.get(job_id)
            if not last_run_str:
                # First time seeing this job, don't consider it missed
                # but record now as the start point.
                self.job_history[job_id] = now.isoformat()
                continue
            
            last_run = datetime.fromisoformat(last_run_str)
            freq = job.get("frequency")
            at_time = job.get("at")
            
            # Simplified missed detection
            missed = False
            reason = ""
            
            if freq == "daily" and at_time:
                hh, mm = map(int, at_time.split(":"))
                scheduled_today = now.replace(hour=hh, minute=mm, second=0, microsecond=0)
                if now > scheduled_today and last_run < scheduled_today:
                    missed = True
                    reason = f"Missed today's {at_time} run"
            elif freq.startswith("every_"):
                parts = freq.split("_")
                val = int(parts[1])
                unit = parts[2]
                delta = None
                if "minute" in unit: delta = timedelta(minutes=val)
                elif "hour" in unit: delta = timedelta(hours=val)
                elif "day" in unit: delta = timedelta(days=val)
                
                if delta and (now - last_run) > delta:
                    missed = True
                    reason = f"Missed interval run (last run: {last_run_str})"
            
            # ... Add weekly/monthly logic if needed ...

            if missed:
                print(f"[Scheduler] Detected missed job: {job.get('summary')} ({job_id}). {reason}.")
                # Trigger it now (it will queue in the priority execution lock)
                self._scheduled_trigger(job.get("agent_id"), f"[MISSED] {job.get('summary')}", job_id)

        self._save_job_history()

    def _scheduled_trigger(self, agent_id: str, summary: str, job_id: str = None):
        """Bridge between schedule library and the orchestration loop."""
        print(f"\n[Scheduler] Triggering scheduled task: {summary} ({agent_id})")
        target = self.active_target or self.get_highest_priority_task()
        if not target:
            print("[Scheduler] No target repository found for scheduled task.")
            return

        routing = target.get("model_routing_preference", "ollama")
        entry = AGENT_REGISTRY.get(agent_id)
        if not entry:
            print(f"[Scheduler] Error: Scheduled agent '{agent_id}' not found in registry.")
            return

        slack_manager.post_message(f"⏰ *Scheduled Task*: {summary}. Waking `{agent_id}`...")
        self.wake_and_execute_agent(
            repo_info=target,
            routing=routing,
            max_steps=20,
            agent_id=agent_id,
            scheduled_prompt=summary
        )

        # Update history AFTER successful (or at least attempted) execution
        if job_id:
            self.job_history[job_id] = datetime.now().isoformat()
            self._save_job_history()

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

    def start_event_listener(self):
        """Starts the event listener thread to watch for priority.json changes."""
        listener_thread = threading.Thread(target=self._watch_config_loop, daemon=True)
        listener_thread.start()
        print("Event listener started. Watching priority.json for updates.")

    def run_fleet_cycle(self):
        """Runs one full cycle through the fleet, processing each repo by priority."""
        print("\nStarting Fleet Cycle...")
        self.is_running_fleet = True
        
        # Periodic Audits
        self.check_compliance_monitoring()

        repos = self.priority_config.get("repositories", [])
        active_repos = [r for r in repos if r.get('agent_status', 'idle') == 'active']
        sorted_repos = sorted(active_repos, key=lambda x: x.get('priority', 999))
        
        for repo_info in sorted_repos:
            if not self.is_running_fleet:
                break
            self.process_repo(repo_info)
        
        print("Fleet Cycle complete.")
        self.is_running_fleet = False



    def process_repo(self, repo_info: Dict[str, Any]):
        """Decides which agent to wake for a given repo based on its current state."""
        repo_path = repo_info.get("repo_path")
        print(f"\nChecking repo: {repo_path}")
        
        # Check if .exegol exists, otherwise trigger Thrawn (onboarding)
        exegol_dir = os.path.join(repo_path, ".exegol")
        if not os.path.exists(exegol_dir):
            print(f"[Onboarding] No .exegol found. Triggering ThoughtfulThrawnAgent...")
            self.wake_and_execute_agent(repo_info, repo_info.get('model_routing_preference', 'ollama'), 5, "thoughtful_thrawn")
            return

        # Check backlog for pending tasks
        backlog_path = os.path.join(exegol_dir, "backlog.json")
        if os.path.exists(backlog_path):
            with open(backlog_path, 'r') as f:
                backlog = json.load(f)
            
            # Check backlog for pending tasks (including prioritized 'todo' tasks)
            pending_tasks = [t for t in backlog if t.get("status") in ["pending_prioritization", "backlogged", "todo"]]
            if pending_tasks:
                print(f"Found {len(pending_tasks)} pending/todo tasks. Triggering ProductPoeAgent...")
                self.wake_and_execute_agent(repo_info, repo_info.get('model_routing_preference', 'ollama'), 10, "product_poe")
                return

        # If it's a Monday or specific time, run review/optimizer (Logic TBD)
        print("💤 Repo is idle.")

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
        # --- SECURITY GUARD: CLI Auth (sec_sec_arch_001) ---
        api_key = os.getenv("EXEGOL_API_KEY")
        if api_key and api_key != "dev-local-key":
             # In a real CLI, we might prompt for a key or check a local token
             # For now, we just log that we are running in authenticated mode
             print("[Orchestrator] Running 'Go' in authenticated CLI mode.")

        print("Received 'Go' trigger. Initiating orchestration cycle...")
        target_repo = self.active_target
        if not target_repo:
            print("No actionable repositories found.")
            return
        
        routing = target_repo.get('model_routing_preference', 'ollama')
        max_steps = target_repo.get('max_steps_policy', 50)
        self.wake_and_execute_agent(target_repo, routing, max_steps)

    def wake_and_execute_agent(self, repo_info: Dict[str, Any], routing: str, max_steps: int,
                                agent_id: str = None, snapshot_hash: str = "", regression_context: str = "",
                                loop_depth: int = 0, chain_history: List[str] = None, scheduled_prompt: str = ""):
        if agent_id is None:
            agent_id = "product_poe"
            
        self.acquire_execution_lock(agent_id)
        result = None
        try:
            result = self._wake_and_execute_agent_inner(
                repo_info, routing, max_steps, agent_id, snapshot_hash, regression_context,
                loop_depth, chain_history, scheduled_prompt
            )
        finally:
            self.release_execution_lock()
            
        if result and getattr(result, "next_agent_id", None) and result.outcome == "success":
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
                    chain_history=current_history
                )
            else:
                print(f"[Orchestrator] Error: Requested next agent '{result.next_agent_id}' not found in registry.")

        return result

    def _wake_and_execute_agent_inner(self, repo_info: Dict[str, Any], routing: str, max_steps: int,
                                agent_id: str = None, snapshot_hash: str = "", regression_context: str = "",
                                loop_depth: int = 0, chain_history: List[str] = None, scheduled_prompt: str = ""):
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
        max_depth = self._get_isolation_setting("max_handoff_depth", 5)
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

        handoff = HandoffContext(
            repo_path=repo_info.get("repo_path", ""),
            agent_id=agent_id,
            task_id="fleet_cycle" if self.is_running_fleet else "manual_go",
            model_routing=routing,
            max_steps=min(max_steps, registry_entry.get("max_steps", 50)),
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
        
        if result:
            path = repo_info.get("repo_path")
            if result.outcome == "failure":
                self.update_repo_status(path, "blocked")
            elif getattr(result, "status_update", ""):
                self.update_repo_status(path, result.status_update)

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
