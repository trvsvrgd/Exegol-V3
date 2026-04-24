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

PRIORITY_FILE_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'config', 'priority.json')

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
        
        # Initialize Slack Listener
        slack_manager.setup_listener(self.handle_wake_word)
        
        # Initialize Autonomous Cadence Engine
        self._setup_cadence_engine()

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
                elif freq.startswith("every_"):
                    # e.g. every_10_minutes
                    parts = freq.split("_")
                    val = int(parts[1])
                    unit = parts[2]
                    if "minute" in unit: s = schedule.every(val).minutes
                    elif "hour" in unit: s = schedule.every(val).hours
                    elif "day" in unit: s = schedule.every(val).days
                
                if at_time:
                    s = s.at(at_time)
                
                s.do(self._scheduled_trigger, agent_id=agent_id, summary=summary)
                print(f"[Scheduler] Registered: {summary} ({agent_id}) @ {freq} {at_time or ''}")

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

    def _scheduled_trigger(self, agent_id: str, summary: str):
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
            max_steps=entry.get("max_steps", 20),
            agent_id=agent_id
        )

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
        
        # Monthly Compliance Check Trigger
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
        
        # Check if .exegol exists, otherwise trigger Thunderbird (onboarding)
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
            
            pending_tasks = [t for t in backlog if t.get("status") in ["pending_prioritization", "backlogged"]]
            if pending_tasks:
                print(f"Found {len(pending_tasks)} pending tasks. Triggering ProductPoeAgent...")
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
                                loop_depth: int = 0, chain_history: List[str] = None):
        """Dispatch an agent through SessionManager for a fully isolated session."""
        if agent_id is None:
            agent_id = "product_poe"
        
        if chain_history is None:
            chain_history = []
        
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
            chain_history=current_history
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

            # Recursive autonomous handoff (Pipeline chaining)
            if result.next_agent_id and result.outcome == "success":
                print(f"[Orchestrator] Autonomous handoff requested: {agent_id} -> {result.next_agent_id}")
                registry_entry = AGENT_REGISTRY.get(result.next_agent_id)
                if registry_entry:
                    # Small delay to ensure logs are flushed and system is ready
                    time.sleep(1)
                    return self.wake_and_execute_agent(
                        repo_info=repo_info,
                        routing=routing,
                        max_steps=registry_entry.get("max_steps", 15),
                        agent_id=result.next_agent_id,
                        snapshot_hash=result.snapshot_hash,
                        regression_context=result.regression_context,
                        loop_depth=current_depth,
                        chain_history=current_history
                    )
                else:
                    print(f"[Orchestrator] Error: Requested next agent '{result.next_agent_id}' not found in registry.")

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
        uar_path = os.path.join(repo_path, ".exegol", "user_action_required.md")
        timestamp = datetime.now().isoformat()
        
        escalation_entry = f"\n- [ ] **BLOCKING ISSUE: {message}**\n  - *Timestamp:* {timestamp}\n  - *Action:* Resolve the agent loop or manually fix the issue to unblock the repository.\n"
        
        try:
            if os.path.exists(uar_path):
                with open(uar_path, 'a', encoding='utf-8') as f:
                    f.write(escalation_entry)
            else:
                os.makedirs(os.path.dirname(uar_path), exist_ok=True)
                with open(uar_path, 'w', encoding='utf-8') as f:
                    f.write("# Exegol V3 - Human Action Required\n")
                    f.write(f"**Generated by:** Orchestrator (Loop Guard)\n")
                    f.write(f"**Timestamp:** {timestamp}\n\n")
                    f.write("> [!CAUTION]\n> A critical loop or depth limit was reached. Autonomous execution is paused for this repo.\n\n")
                    f.write("## 🚨 Critical Escalations\n")
                    f.write(escalation_entry)
            
            print(f"[Orchestrator] Escalated to human: {message}")
        except Exception as e:
            print(f"[Orchestrator] Failed to escalate to human: {e}")

    def handle_wake_word(self, command_string: str, channel: str = None):
        """Processes CLI input to trigger specific agents or default 'go' behavior."""
        cmd = command_string.lower()

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
                slack_manager.post_message("❌ Please provide a task description. Example: `add to backlog review PRs`", channel=channel)
                return

            target = self.active_target or {"repo_path": os.path.dirname(os.path.dirname(__file__))}
            repo_path = target.get("repo_path")
            
            bm = BacklogManager(repo_path)
            new_task = {
                "id": str(uuid.uuid4()),
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
            if details["wake_word"] in cmd:
                print(f"Triggering specific agent: {agent_id} by wake word '{details['wake_word']}'")
                slack_manager.post_message(f"🤖 Waking `{agent_id}`...", channel=channel)
                target = self.active_target or {"repo_path": os.path.dirname(os.path.dirname(__file__))}
                routing = target.get("model_routing_preference", "ollama")
                self.wake_and_execute_agent(
                    repo_info=target,
                    routing=routing,
                    max_steps=details["max_steps"],
                    agent_id=agent_id,
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
            f"❓ Unknown command: `{command_string}`\nTry: `go`, `fleet`, or an agent wake word.",
            channel=channel
        )

    def shutdown(self):
        """Performs a clean shutdown of the orchestrator and its background threads."""
        print("[Shutdown] Initiating graceful shutdown...")
        self._should_stop_scheduler = True
        self.is_running_fleet = False
        
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
