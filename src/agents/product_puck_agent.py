import os
import json


class ProductPuckAgent:
    """Manages the backlog, grooms requirements, and transforms them into effective prompts for other agents."""

    def __init__(self, llm_client):
        self.llm_client = llm_client
        self.name = "ProductivePuckAgent"
        self.max_steps = 10
        self.tools = ["backlog_grooming", "prompt_generation"]
        self.success_metrics = {
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

        Reads backlog from filesystem, grooms it, and writes the active prompt.
        """
        repo_path = handoff.repo_path
        print(f"[{self.name}] Session {handoff.session_id} — waking up for repo: {repo_path}")
        print(f"[{self.name}] Grooming backlog and transforming requirements into developer prompts...")

        exegol_dir = os.path.join(repo_path, ".exegol")
        os.makedirs(exegol_dir, exist_ok=True)

        backlog_file = os.path.join(exegol_dir, "backlog.json")
        prompt_file = os.path.join(exegol_dir, "active_prompt.md")

        backlog = []
        if os.path.exists(backlog_file):
            try:
                with open(backlog_file, 'r', encoding='utf-8') as f:
                    backlog = json.load(f)
            except Exception as e:
                print(f"[{self.name}] Error reading backlog: {e}")

        # Mock logic to add a task to backlog
        task = {
            "id": f"t_{len(backlog)+1:03d}",
            "summary": "Implement basic feature",
            "priority": "high",
            "status": "in_progress"
        }
        backlog.append(task)

        with open(backlog_file, 'w', encoding='utf-8') as f:
            json.dump(backlog, f, indent=4)

        active_prompt = f"# Active Developer Task\n\n**Task ID:** {task['id']}\n**Priority:** {task['priority']}\n\n## Instructions\n{task['summary']}\n"
        with open(prompt_file, 'w', encoding='utf-8') as f:
            f.write(active_prompt)

        return f"Backlog updated in {backlog_file} and {prompt_file} generated."
