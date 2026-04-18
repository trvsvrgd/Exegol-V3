import os


class DeveloperDragonAgent:
    """Executes agentic coding tasks based on provided prompts, aiming for minimal iteration loops."""

    def __init__(self, llm_client):
        self.llm_client = llm_client
        self.name = "DeveloperDragonAgent"
        self.max_steps = 20
        self.tools = ["file_editor", "slack_notifier", "agentic_coding"]
        self.success_metrics = {
            "bugs_found_in_qa": {
                "description": "Number of bugs caught by QA per coding cycle",
                "target": "0",
                "current": None
            },
            "avg_prompts_to_acceptance": {
                "description": "Average number of prompt-loop iterations to meet acceptance criteria",
                "target": "<=2",
                "current": None
            },
            "code_churn_rate": {
                "description": "Percentage of lines rewritten within the same sprint",
                "target": "<=10%",
                "current": None
            }
        }
        self.system_prompt = self.llm_client.generate_system_prompt(self)


    def execute(self, handoff):
        """Execute with a clean HandoffContext — no prior session memory required.

        Reads the active prompt from the filesystem. Needs nothing else.
        """
        repo_path = handoff.repo_path
        print(f"[{self.name}] Session {handoff.session_id} — waking up for repo: {repo_path}")

        prompt_file = os.path.join(repo_path, ".exegol", "active_prompt.md")
        if os.path.exists(prompt_file):
            try:
                with open(prompt_file, 'r', encoding='utf-8') as f:
                    active_prompt = f.read()
                print(f"[{self.name}] Reading active prompt:\n{active_prompt}")
                # Mock coding action
                return f"Coding tasks executed for prompt from {prompt_file}."
            except Exception as e:
                return f"[{self.name}] Error reading prompt: {e}"
        else:
            print(f"[{self.name}] No active prompt found.")
            return "No prompt found in .exegol/active_prompt.md"
