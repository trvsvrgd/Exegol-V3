import os
import json
from tools.thrawn_intel_manager import ThrawnIntelManager
from tools.web_search import web_search


class ThoughtfulThrawnAgent:
    """Orchestrates the repository onboarding process, asks clarifying questions, and identifies project intent."""

    def __init__(self, llm_client):
        self.llm_client = llm_client
        self.name = "ThoughtfulThrawnAgent"
        self.max_steps = 5
        self.tools = ["user_prompting", "clarification_engine", "markdown_sync", "web_search"]
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

        # 1. Load Intent & Clarifications via Manager (Stateless Refactor)
        mgr = ThrawnIntelManager(repo_path)
        intel = mgr.read_intent()
        
        # Phase 2: Web Search for Intent Enrichment
        if intel.get("objective") and intel.get("objective") != "[Describe the main goal of this repository]":
            print(f"[{self.name}] Researching context for objective: {intel['objective']}")
            search_query = f"industry standards and technical requirements for: {intel['objective']}"
            context_research = web_search(search_query, num_results=3)
            # This research can be used by the LLM in the next steps

        # 2. Identify Open Questions from parsed intel
        open_questions = [q["question"] for q in intel["questions"] if not q["answer"]]
        
        # 3. Synchronize Answered Questions with Roadmap
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
            sync_response = self.llm_client.generate(sync_prompt, system_instruction=self.system_prompt)
            actions = self._parse_and_validate_sync_actions(sync_response)
            for action in actions:
                if action["action"] == "redact":
                    mgr.redact_roadmap_item(action["pattern"])
                elif action["action"] == "add":
                    mgr.add_roadmap_item(action["section"], action["item"])

        if not open_questions:
            # If no open questions, maybe do a general checkup
            prompt = f"The current intent for the repository at {repo_path} is:\n{content}\n\nReview this intent. Is it clear? Are there any missing architectural details or potential risks? If so, generate 1-3 strategic questions. If it's perfect, say 'The strategy is sound.'"
            response = self.llm_client.generate(prompt, system_instruction=self.system_prompt)
            
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

    def _parse_and_validate_sync_actions(self, response: str) -> list:
        """Extracts JSON from LLM response and validates against sync schema."""
        import jsonschema
        
        schema = {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "action": {"type": "string", "enum": ["redact", "add"]},
                    "pattern": {"type": "string"},
                    "section": {"type": "string"},
                    "item": {"type": "string"}
                },
                "required": ["action"],
                "if": {
                    "properties": {"action": {"const": "redact"}}
                },
                "then": {
                    "required": ["pattern"]
                },
                "else": {
                    "if": {
                        "properties": {"action": {"const": "add"}}
                    },
                    "then": {
                        "required": ["section", "item"]
                    }
                }
            }
        }
        
        # Use common robust parser from LLMClient
        data = self.llm_client.parse_json_response(response)
        
        if not isinstance(data, list):
            # If it's a dict with the list inside (common LLM failure)
            if isinstance(data, dict):
                for val in data.values():
                    if isinstance(val, list):
                        data = val
                        break
        
        if not isinstance(data, list):
            print(f"[{self.name}] ERROR: Expected list of actions, got {type(data)}")
            return []
            
        validated_actions = []
        for action in data:
            try:
                jsonschema.validate(instance=action, schema=schema)
                validated_actions.append(action)
            except jsonschema.exceptions.ValidationError as e:
                print(f"[{self.name}] WARNING: Skipping invalid action: {e.message}")
                
        return validated_actions

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

