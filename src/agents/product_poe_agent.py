import os
import json
import time
from tools.fleet_logger import log_interaction
from tools.backlog_manager import BacklogManager


class ProductPoeAgent:
    """Manages the project backlog, prioritizes tasks, and orchestrates the 'Idea-to-Production' low-code lifecycle.
    
    Responsible for transforming high-level user ideas into structured app definitions (app.exegol.json)
    and managing the backlog for local deployment and inference.
    """

    def __init__(self, llm_client):
        self.llm_client = llm_client
        self.name = "ProductPoeAgent"
        self.max_steps = 10
        self.tools = ["backlog_grooming", "prompt_generation", "app_scaffolding"]
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

            task, source = self._select_next_task(backlog)

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

            active_prompt = self._generate_active_prompt(task, repo_path)
            
            with open(prompt_file, 'w', encoding='utf-8') as f:
                f.write(active_prompt)

            self.next_agent_id = "developer_dex"
            res = f"Active task set: {task.get('id')} ({task.get('summary')}). Handing off to DeveloperDex."
            
            duration = time.time() - start_time
            log_interaction(
                agent_id=self.name,
                outcome="success",
                task_summary=res,
                repo_path=repo_path,
                steps_used=1,
                duration_seconds=duration,
                session_id=handoff.session_id
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

    def _select_next_task(self, backlog):
        # 1. Backlog 'todo' or 'backlogged' (Prioritize High/Critical)
        for t in backlog:
            if t.get("status") in ["todo", "backlogged", "pending_prioritization"]:
                if t.get("priority") in ["critical", "high"]:
                    return t, "backlog"

        # 2. Any other 'todo' backlog items
        for t in backlog:
            if t.get("status") in ["todo", "backlogged", "pending_prioritization"]:
                return t, "backlog"

        return None, None

    def _generate_active_prompt(self, task, repo_path):
        """Uses LLM to context-enrich the task summary into a developer prompt."""
        context_prompt = f"""
        Expand this task into a detailed developer instruction set.
        Task Summary: {task.get('summary')}
        Task Description: {task.get('description', 'N/A')}
        Repository: {repo_path}
        
        Include relevant files to check and a step-by-step implementation plan.
        """
        try:
            response = self.llm_client.generate(context_prompt, system_instruction=self.system_prompt)
            return f"# Active Developer Task\n\n**Task ID:** {task.get('id')}\n\n{response}"
        except Exception:
            # Fallback
            return f"# Active Developer Task\n\n**Task ID:** {task.get('id')}\n\n## Instructions\n{task.get('summary')}\n"
