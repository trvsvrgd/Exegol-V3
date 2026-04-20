import json
import os
import time
import threading
import sys
from dotenv import load_dotenv

# Load environment variables before any other imports
load_dotenv()

from typing import Dict, Any, List
from agents.registry import AGENT_REGISTRY
from handoff import HandoffContext
from session_manager import SessionManager
from tools.slack_tool import slack_manager

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
        
        # Initialize Slack Listener
        slack_manager.setup_listener(self.handle_wake_word)

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
            print(f"[Onboarding] No .exegol found. Triggering OnboardingThrawnAgent...")
            self.wake_and_execute_agent(repo_info, repo_info.get('model_routing_preference', 'ollama'), 5, "onboarding_thrawn")
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
                                agent_id: str = None, snapshot_hash: str = "", regression_context: str = ""):
        """Dispatch an agent through SessionManager for a fully isolated session."""
        if agent_id is None:
            agent_id = "product_poe"

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
            regression_context=regression_context
        )

        result = self.session_manager.spawn_agent_session(
            agent_id=agent_id,
            module_path=registry_entry["module"],
            class_name=registry_entry["class"],
            handoff=handoff,
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
                        regression_context=result.regression_context
                    )
                else:
                    print(f"[Orchestrator] Error: Requested next agent '{result.next_agent_id}' not found in registry.")

        return result

    def handle_wake_word(self, command_string: str, channel: str = None):
        """Processes CLI input to trigger specific agents or default 'go' behavior."""
        cmd = command_string.lower()

        if "fleet" in cmd:
            slack_manager.post_message("🚀 Fleet cycle starting — processing all active repos...", channel=channel)
            self.run_fleet_cycle()
            slack_manager.post_message("✅ Fleet cycle complete.", channel=channel)
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
            os._exit(0)

        if "go" in cmd:
            slack_manager.post_message("🚀 `go` received — triggering active repository...", channel=channel)
            self.trigger_go()
            return

        print(f"Unknown command or wake word in: '{command_string}'")
        slack_manager.post_message(
            f"❓ Unknown command: `{command_string}`\nTry: `go`, `fleet`, or an agent wake word.",
            channel=channel
        )

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
