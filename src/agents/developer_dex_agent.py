import os
import json
from tools.sandbox_orchestrator import create_sandbox, deploy_to_sandbox
from tools.file_editor_tool import read_file, write_file, replace_content, search_replace_regex, delete_file
from tools.snapshot_tester import capture_snapshot


class DeveloperDexAgent:
    """Writes code, performs edits, and orchestrates 'Experience Sandboxes' for rapid prototyping.
    
    Responsible for implementing schema-defined applications into isolated sandbox environments
    to enable user feedback (HITL) before production deployment.
    """

    def __init__(self, llm_client):
        self.llm_client = llm_client
        self.name = "DeveloperDexAgent"
        self.max_steps = 20
        self._steps_used = 0
        self.snapshot_hash = ""
        self.tools = ["file_editor", "slack_notifier", "agentic_coding", "sandbox_orchestrator"]
        self.success_metrics = {
            "sandbox_acceptance_rate": {
                "description": "Percentage of user feedback sessions in sandboxes resulting in 'approved' status",
                "target": ">=80%",
                "current": None
            },
            "bugs_found_in_qa": {
                "description": "Number of bugs caught by QualityQuigon per coding cycle",
                "target": "0",
                "current": None
            },
            "avg_prompts_to_acceptance": {
                "description": "Average number of prompt-loop iterations to meet acceptance criteria",
                "target": "<=2",
                "current": None
            }
        }
        self.system_prompt = self.llm_client.generate_system_prompt(self)

    def execute(self, handoff):
        """Execute with a clean HandoffContext — no prior session memory required."""
        self._steps_used = 0
        repo_path = handoff.repo_path
        print(f"[{self.name}] Session {handoff.session_id} — waking up for repo: {repo_path}")

        prompt_file = os.path.join(repo_path, ".exegol", "active_prompt.md")
        if not os.path.exists(prompt_file):
            print(f"[{self.name}] No active prompt found.")
            return "No prompt found in .exegol/active_prompt.md"

        try:
            with open(prompt_file, 'r', encoding='utf-8') as f:
                active_prompt = f.read()
            
            print(f"[{self.name}] Analyzing prompt: {active_prompt[:100]}...")

            if "prototype" in active_prompt.lower() or "sandbox" in active_prompt.lower():
                return self._handle_sandbox_request(repo_path, active_prompt)
            
            # Real coding loop
            return self._run_coding_loop(repo_path, active_prompt, handoff)
            
        except Exception as e:
            return f"[{self.name}] Error during execution: {e}"

    def _handle_sandbox_request(self, repo_path, active_prompt):
        print(f"[{self.name}] Prototyping request detected. Scaffolding sandbox...")
        app_id = "demo_app"  # In a real run, this would be parsed from the prompt or schema
        sandbox_path = create_sandbox(repo_path, app_id)
        
        # Deploy boilerplate
        files = {
            "index.html": "<h1>Hello from Exegol Sandbox</h1>",
            "app.js": "console.log('Sandbox app running');"
        }
        deploy_to_sandbox(sandbox_path, files)
        self._steps_used += 1
        return f"Experience Sandbox created at: {sandbox_path}. Prototype deployed."

    def _run_coding_loop(self, repo_path, active_prompt, handoff):
        """Standard coding actions using LLM to plan and tools to execute."""
        print(f"[{self.name}] Initiating coding cycle...")
        
        # Step 1: Analyze and Plan
        regression_note = f"\nREGRESSION WARNING: {handoff.regression_context}" if handoff.regression_context else ""
        planning_prompt = f"""
        User Task: {active_prompt}
        {regression_note}
        
        Existing Files in Repo: {os.listdir(repo_path)}
        
        Plan the necessary file modifications. Return a JSON list of actions.
        Each action should be:
        {{
            "type": "write" | "replace",
            "path": "relative/path/to/file",
            "content": "new content" | "text to insert",
            "target": "text to replace" (only for type: replace)
        }}
        """
        
        response = self.llm_client.generate(planning_prompt, system_instruction=self.system_prompt, json_format=True)
        actions = self.llm_client.parse_json_response(response)
        
        if not actions or not isinstance(actions, list):
            # Fallback if JSON parsing fails or gives empty list
            return "Failed to parse coding plan from LLM."

        results = []
        for action in actions:
            if self._steps_used >= self.max_steps:
                break
                
            file_path = os.path.join(repo_path, action.get("path", ""))
            action_type = action.get("type")
            
            if action_type == "write":
                res = write_file(file_path, action.get("content", ""))
                results.append(f"Write {action.get('path')}: {res}")
            elif action_type == "replace":
                res = replace_content(file_path, action.get("target", ""), action.get("content", ""))
                results.append(f"Replace in {action.get('path')}: {res}")
            
            self._steps_used += 1

        res = f"Coding cycle complete. Results:\n" + "\n".join(results)
        
        # Capture snapshot for regression testing (poe_009)
        snapshot_data = {
            "task_id": getattr(handoff, "task_id", "unknown"),
            "agent": self.name,
            "actions_planned": actions,
            "results": results,
            "summary": res
        }
        try:
            # Use task_id as the primary snapshot name for regression tracking
            snapshot_name = f"dex_{snapshot_data['task_id']}"
            self.snapshot_hash = capture_snapshot(snapshot_data, snapshot_name)
            print(f"[{self.name}] Snapshot captured: {self.snapshot_hash}")
        except Exception as e:
            print(f"[{self.name}] Failed to capture snapshot: {e}")

        self.next_agent_id = "quality_quigon"
        return res

