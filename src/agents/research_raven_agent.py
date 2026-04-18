import os
import json


class ResourcefulRavenAgent:
    """Researches latest models (especially local open-source) and recommends upgrades for agent tasks."""

    def __init__(self, llm_client):
        self.llm_client = llm_client
        self.name = "ResourcefulRavenAgent"
        self.max_steps = 10
        self.tools = ["model_comparison", "web_search", "backlog_writer"]
        self.success_metrics = {
            "model_recommendations_adopted": {
                "description": "Percentage of model upgrade suggestions accepted by the team",
                "target": ">=50%",
                "current": None
            },
            "research_freshness_days": {
                "description": "Days since the last model landscape scan was completed",
                "target": "<=14",
                "current": None
            }
        }
        self.system_prompt = self.llm_client.generate_system_prompt(self)

    def execute(self, handoff):
        """Execute with a clean HandoffContext — no prior session memory required.

        Reads backlog from filesystem, researches models, writes upgrades back.
        """
        repo_path = handoff.repo_path
        print(f"[{self.name}] Session {handoff.session_id} — waking up for repo: {repo_path}")
        print(f"[{self.name}] Researching latest models (especially local open-source) suitable for given tasks...")

        exegol_dir = os.path.join(repo_path, ".exegol")
        os.makedirs(exegol_dir, exist_ok=True)

        backlog_file = os.path.join(exegol_dir, "backlog.json")

        backlog = []
        if os.path.exists(backlog_file):
            try:
                with open(backlog_file, 'r', encoding='utf-8') as f:
                    backlog = json.load(f)
            except Exception as e:
                print(f"[{self.name}] Error reading backlog: {e}")

        # Mock logic to add a model upgrade task to backlog
        task = {
            "id": f"t_{len(backlog)+1:03d}",
            "summary": "Evaluate and update agent model (e.g., Llama-3 over Llama-2 for local agentic tasks)",
            "priority": "medium",
            "type": "model_upgrade",
            "status": "pending_prioritization"
        }
        backlog.append(task)

        with open(backlog_file, 'w', encoding='utf-8') as f:
            json.dump(backlog, f, indent=4)

        return f"Model upgrade research completed. Task added to {backlog_file}."
