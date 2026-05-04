import os
import json
import time
from tools.fleet_logger import log_interaction
from tools.backlog_manager import BacklogManager
from tools.web_search import web_search
from tools.backlog_groomer import select_next_task
from tools.prompt_generator import generate_active_prompt
from tools.metrics_manager import SuccessMetricsManager
from tools.heartbeat_monitor import HeartbeatMonitor


class ProductPoeAgent:
    """Manages the project backlog, prioritizes tasks, and orchestrates the 'Idea-to-Production' low-code lifecycle.
    
    Responsible for transforming high-level user ideas into structured app definitions (app.exegol.json)
    and managing the backlog for local deployment and inference.
    """

    def __init__(self, llm_client):
        self.llm_client = llm_client
        self.name = "ProductPoeAgent"
        self.max_steps = 10
        self.tools = ["backlog_grooming", "prompt_generation", "app_scaffolding", "web_search"]
        self.success_metrics = {
            "app_definition_readiness": {
                "description": "Percentage of user ideas successfully transformed into valid app.exegol.json schemas",
                "target": "100%",
                "current": None
            },
            "backlog_grooming_completeness": {
                "description": "Percentage of backlog items with acceptance criteria defined",
                "target": "100%",
                "current": None
            },
            "prompt_rejection_rate": {
                "description": "Percentage of generated prompts rejected by developer agent",
                "target": "<=5%",
                "current": None
            }
        }
        self.system_prompt = self.llm_client.generate_system_prompt(self)
        self.metrics_manager = SuccessMetricsManager(os.getcwd())

    def _calculate_success_metrics(self, repo_path: str) -> dict:
        """Calculates grooming and readiness metrics based on recent logs."""
        logs = self.metrics_manager.load_logs(days=7)
        agent_logs = [l for l in logs if l.get("agent_id") == self.name]
        
        if not agent_logs:
            return {
                "app_definition_readiness": 0.0,
                "backlog_grooming_completeness": 0.0,
                "prompt_rejection_rate": 0.0
            }

        successful_runs = [l for l in agent_logs if l.get("outcome") == "success"]
        readiness = len(successful_runs) / len(agent_logs) if agent_logs else 0.0
        
        # Heuristic for grooming: count tasks in 'in_progress' or 'completed'
        bm = BacklogManager(repo_path)
        backlog = bm.load_backlog()
        total_tasks = len(backlog)
        groomed_tasks = len([t for t in backlog if t.get("status") in ["in_progress", "completed"]])
        grooming_completeness = groomed_tasks / total_tasks if total_tasks else 1.0

        # Heuristic for rejection: check logs for 'retry' or 'rejected' keywords in task summaries
        rejections = len([l for l in logs if "rejected" in l.get("task_summary", "").lower()])
        total_prompts = len([l for l in agent_logs if "prompt" in l.get("task_summary", "").lower()])
        rejection_rate = rejections / total_prompts if total_prompts else 0.0

        return {
            "app_definition_readiness": round(readiness * 100, 1),
            "backlog_grooming_completeness": round(grooming_completeness * 100, 1),
            "prompt_rejection_rate": round(rejection_rate * 100, 1)
        }


    def execute(self, handoff):
        """Execute with a clean HandoffContext — no prior session memory required.

        Reads backlog from filesystem, selects the next task, 
        and writes the active prompt.
        """
        start_time = time.time()
        repo_path = handoff.repo_path
        print(f"[{self.name}] Session {handoff.session_id} — waking up for repo: {repo_path}")

        exegol_dir = os.path.join(repo_path, ".exegol")
        os.makedirs(exegol_dir, exist_ok=True)
        
        backlog_file = os.path.join(exegol_dir, "backlog.json")
        prompt_file = os.path.join(exegol_dir, "active_prompt.md")

        try:
            bm = BacklogManager(repo_path)
            backlog = bm.load_backlog()

            # 1. Check for external instruction (from Slack/Scheduler)
            if handoff.scheduled_prompt:
                print(f"[{self.name}] Received scheduled prompt: {handoff.scheduled_prompt}")
                task = {
                    "id": f"poe_{int(time.time())}",
                    "summary": handoff.scheduled_prompt,
                    "priority": "high",
                    "status": "todo",
                    "source": "slack"
                }
                source = "external"
                # Save to backlog for tracking
                bm.add_task(task)
            else:
                task, source = select_next_task(backlog)

            if not task:
                print(f"[{self.name}] No actionable tasks found in backlog or vibe_todo.")
                # Fallback: Create a maintenance task
                task = {
                    "id": "maint_001",
                    "summary": "General codebase health check and documentation update",
                    "priority": "low",
                    "status": "todo"
                }
                source = "fallback"

            print(f"[{self.name}] Selected task {task.get('id')} from {source}: {task.get('summary')}")

            # Update backlog status if it was from backlog
            if source == "backlog":
                bm.update_task_status(task.get("id"), "in_progress")

            # Pulse heartbeat (arch_agent_heartbeat)
            HeartbeatMonitor.pulse_session(repo_path, handoff.session_id)

            active_prompt = generate_active_prompt(task, repo_path, self.llm_client, self.system_prompt)
            
            with open(prompt_file, 'w', encoding='utf-8') as f:
                f.write(active_prompt)

            # Dynamic Handoff Routing
            if task.get("type") == "analysis" or "analyze" in task.get("summary", "").lower():
                self.next_agent_id = "architect_artoo"
            else:
                self.next_agent_id = "developer_dex"

            res = f"Active task set: {task.get('id')} ({task.get('summary')}). Handing off to {self.next_agent_id}."
            
            duration = time.time() - start_time
            metrics = self._calculate_success_metrics(repo_path)
            
            log_interaction(
                agent_id=self.name,
                outcome="success",
                task_summary=res,
                repo_path=repo_path,
                steps_used=1,
                duration_seconds=duration,
                session_id=handoff.session_id,
                metrics=metrics
            )
            return res
            
        except Exception as e:
            duration = time.time() - start_time
            log_interaction(
                agent_id=self.name,
                outcome="failure",
                task_summary=f"Task selection failed: {str(e)}",
                repo_path=repo_path,
                steps_used=1,
                duration_seconds=duration,
                errors=[str(e)],
                session_id=handoff.session_id
            )
            return f"[{self.name}] Error during backlog grooming: {e}"

