import os
import json
from tools.thrawn_intel_manager import ThrawnIntelManager


class ThoughtfulThrawnAgent:
    """Orchestrates the repository onboarding process, asks clarifying questions, and identifies project intent."""

    def __init__(self, llm_client):
        self.llm_client = llm_client
        self.name = "ThoughtfulThrawnAgent"
        self.max_steps = 5
        self.tools = ["user_prompting", "clarification_engine", "markdown_sync"]
        self.restrictions = [
            "Cannot modify code files (*.py, *.js, etc.)",
            "Cannot modify agent definitions",
            "Authorized only for .exegol/*.md and root README.md"
        ]
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
        intent_file = os.path.join(exegol_dir, "intent.md")

        # 1. Load Intent & Clarifications
        if not os.path.exists(intent_file):
            print(f"[{self.name}] CRITICAL: No intent.md found. Creating boilerplate...")
            self._create_boilerplate_intent(intent_file)
            return "Boilerplate intent.md created. Please fill it out."

        with open(intent_file, 'r', encoding='utf-8') as f:
            content = f.read()

        # 2. Identify Open Questions
        open_questions = []
        in_questions_section = False
        current_question = None
        
        for line in content.splitlines():
            if "Open Clarification Questions" in line:
                in_questions_section = True
                continue
            
            if in_questions_section:
                if line.startswith("##"):
                    in_questions_section = False
                    continue
                
                stripped = line.strip()
                if not stripped:
                    continue
                
                # Check for new question
                if stripped[0].isdigit() or stripped.startswith("-"):
                    if current_question and "Answer:" not in current_question:
                        open_questions.append(current_question)
                    current_question = stripped
                elif "Answer:" in stripped:
                    if current_question:
                        current_question += " " + stripped
                elif current_question:
                    current_question += " " + stripped

        # Handle the last question
        if in_questions_section and current_question:
            if "Answer:" not in current_question:
                open_questions.append(current_question)
            else:
                # Store answered questions for potential roadmap sync
                pass # We'll handle this via IntelManager

        # 3. Synchronize Answered Questions with Roadmap
        mgr = ThrawnIntelManager(repo_path)
        intel = mgr.read_intent()
        answered_questions = [q for q in intel["questions"] if q["answer"]]
        
        if answered_questions:
            roadmap_content = mgr.read_roadmap()
            sync_prompt = f"""
You are {self.name}. The user has answered the following strategic questions:
{json.dumps(answered_questions, indent=2)}

Current Roadmap:
{roadmap_content}

Based on the user's answers, should any items be redacted, added, or updated in the roadmap?
If an answer says "No" or suggests against a feature, redact it.
Return a list of specific actions in JSON format:
[{{"action": "redact", "pattern": "string to match"}}, {{"action": "add", "section": "Phase X", "item": "new item"}}]
If no changes needed, return [].
"""
            sync_response = self.llm_client.generate_response(sync_prompt, system_prompt=self.system_prompt)
            try:
                # Extract JSON from response
                start = sync_response.find("[")
                end = sync_response.rfind("]") + 1
                actions = json.loads(sync_response[start:end])
                for action in actions:
                    if action["action"] == "redact":
                        mgr.redact_roadmap_item(action["pattern"])
                    # TODO: Implement 'add' and 'update' in mgr if needed
            except:
                print(f"[{self.name}] Failed to parse sync actions from LLM.")

        if not open_questions:
            # If no open questions, maybe do a general checkup
            prompt = f"The current intent for the repository at {repo_path} is:\n{content}\n\nReview this intent. Is it clear? Are there any missing architectural details or potential risks? If so, generate 1-3 strategic questions. If it's perfect, say 'The strategy is sound.'"
            response = self.llm_client.generate_response(prompt, system_prompt=self.system_prompt)
            
            if "The strategy is sound" not in response:
                # Add new questions to intent.md
                mgr = ThrawnIntelManager(repo_path)
                intel = mgr.read_intent()
                # Simple extraction of questions from response
                new_qs = [line.strip() for line in response.splitlines() if "?" in line]
                for nq in new_qs:
                    intel["questions"].append({"question": nq, "answer": None})
                mgr.save_intent(intel)
                return f"[{self.name}] Strategic review complete. Added {len(new_qs)} new questions."
            
            return f"[{self.name}] All clarifications resolved. Strategy is sound."

        # 3. Notify Slack (Non-blocking)
        from tools.slack_tool import post_to_slack
        msg = f"🤔 *Thrawn Strategic Update*: `{repo_path}`\nThere are {len(open_questions)} open questions.\n\n*Top Priority*:\n_{open_questions[0]}_\n\n_Please provide answers in the Workbench UI to unblock the fleet._"
        post_to_slack(msg)

        return f"[{self.name}] Notified user via Slack. Waiting for further input."

    def _create_boilerplate_intent(self, path):
        boilerplate = """# 🚀 Repository Intent & Clarifications

## 🎯 Primary Objective
[Describe the main goal of this repository]

## 🏗️ Architecture & Patterns
- [Pattern 1]
- [Pattern 2]

## ❓ Open Clarification Questions (Active Grooming)
1. What is the target deployment environment?
2. Should we prioritize speed or cost for LLM inference?
"""
        with open(path, 'w', encoding='utf-8') as f:
            f.write(boilerplate)

