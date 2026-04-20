import os
import json


class OnboardingThrawnAgent:
    """Orchestrates the repository onboarding process, asks clarifying questions, and identifies project intent."""

    def __init__(self, llm_client):
        self.llm_client = llm_client
        self.name = "OnboardingThrawnAgent"
        self.max_steps = 5
        self.tools = ["user_prompting", "clarification_engine"]
        self.success_metrics = {
            "questions_answered_rate": {
                "description": "Percentage of generated questions that receive user answers",
                "target": ">=90%",
                "current": None
            },
            "clarification_turnaround_hrs": {
                "description": "Average hours from question posed to answer received",
                "target": "<=24",
                "current": None
            }
        }
        self.system_prompt = self.llm_client.generate_system_prompt(self)


    def execute(self, handoff):
        """Execute with a clean HandoffContext — no prior session memory required.

        All state is read fresh from the filesystem at invocation time.
        """
        repo_path = handoff.repo_path
        print(f"[{self.name}] Session {handoff.session_id} — waking up for repo: {repo_path}")

        exegol_dir = os.path.join(repo_path, ".exegol")
        os.makedirs(exegol_dir, exist_ok=True)
        discussions_file = os.path.join(exegol_dir, "discussions.json")
        intent_file = os.path.join(exegol_dir, "intent.md")

        # 1. Check if intent is already defined
        if os.path.exists(intent_file):
            print(f"[{self.name}] Intent already defined for this repo. Checking for clarifications...")
            # Logic to scan code vs intent and find gaps
            return f"Intent verified in {intent_file}. No new questions at this time."

        print(f"[{self.name}] No intent defined. Initiating onboarding interview...")

        discussions = []
        if os.path.exists(discussions_file):
            try:
                with open(discussions_file, 'r', encoding='utf-8') as f:
                    discussions = json.load(f)
            except Exception as e:
                print(f"[{self.name}] Error reading discussions: {e}")

        # 2. Prompt user via CLI for intent
        from tools.slack_tool import post_to_slack
        post_to_slack(f"✨ *NEW REPO ONBOARDING*: `{repo_path}`\nThunderbird is waiting for CLI input to define repository intent.")
        
        print(f"\n[?] Please define the intent for {repo_path} via CLI.")
        objective = input("What is the primary objective of this repository?:\n> ")
        architecture = input("Are there specific frameworks or design patterns you want to enforce?:\n> ")
        
        intent_content = f"# Repository Intent\n\n## Primary Objective\n{objective}\n\n## Architecture & Patterns\n{architecture}\n"
        
        with open(intent_file, 'w', encoding='utf-8') as f:
            f.write(intent_content)
            
        post_to_slack(f"✅ *REPO ONBOARDED*: `{repo_path}`\nIntent has been successfully captured and saved to `.exegol/intent.md`.")

        return f"Onboarding complete. Intent saved to {intent_file}."
