import os
import json
import time
from tools.fleet_logger import log_interaction
from tools.backlog_manager import BacklogManager
from tools.web_search import web_search
from tools.backlog_groomer import select_next_task
from tools.prompt_generator import generate_active_prompt


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

            active_prompt = generate_active_prompt(task, repo_path, self.llm_client, self.system_prompt)
            
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

