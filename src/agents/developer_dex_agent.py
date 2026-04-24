import os
import json
import time
from dataclasses import dataclass
from typing import Optional
from tools.sandbox_orchestrator import create_sandbox, deploy_to_sandbox
from tools.sandbox_validator import validate_app_schema
from tools.file_editor_tool import read_file, write_file, replace_content, search_replace_regex, delete_file
from tools.snapshot_tester import capture_snapshot
from tools.fleet_logger import log_interaction
from tools.input_sanitizer import sanitize_prompt
from tools.security_audit_logger import log_security_event


# ---------------------------------------------------------------------------
# Task 3 — CodingAction Dataclass (arch_dex_integration_sync)
# ---------------------------------------------------------------------------

@dataclass
class CodingAction:
    """Typed representation of a single LLM-planned coding operation.

    Ensures all actions dispatched to file_editor_tool are schema-validated
    before execution, preventing raw-dict runtime errors.
    """
    type: str           # "write" | "replace"
    path: str           # Relative path inside repo
    content: str        # New content (write) or replacement text (replace)
    target: str = ""    # Text to replace (only for type: "replace")


def _validate_action(action: dict) -> Optional[CodingAction]:
    """Coerce an LLM dict into a CodingAction, returning None on schema failure."""
    action_type = action.get("type")
    path = action.get("path", "").strip()
    content = action.get("content", "")

    if action_type not in ("write", "replace"):
        print(f"[DeveloperDexAgent] WARNING: Skipping action with unknown type '{action_type}'")
        return None
    if not path:
        print(f"[DeveloperDexAgent] WARNING: Skipping action with empty path.")
        return None
    if content is None:
        print(f"[DeveloperDexAgent] WARNING: Skipping action with missing content.")
        return None

    return CodingAction(
        type=action_type,
        path=path,
        content=str(content),
        target=str(action.get("target", "")),
    )


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

    def _validate_action_path(self, repo_path: str, relative_path: str) -> bool:
        """Security Guard: Ensures the target path is within the repo boundary."""
        if not relative_path or not relative_path.strip():
            return False
        
        # Resolve absolute paths and remove .. segments
        abs_path = os.path.realpath(os.path.join(repo_path, relative_path))
        repo_root = os.path.realpath(repo_path)
        
        # Check if the resolved path starts with the repo root
        return abs_path.startswith(repo_root + os.sep) or abs_path == repo_root

    def execute(self, handoff):
        """Execute with a clean HandoffContext — no prior session memory required."""
        start_time = time.time()
        self._steps_used = 0
        repo_path = handoff.repo_path
        print(f"[{self.name}] Session {handoff.session_id} — waking up for repo: {repo_path}")

        prompt_file = os.path.join(repo_path, ".exegol", "active_prompt.md")
        if not os.path.exists(prompt_file):
            print(f"[{self.name}] No active prompt found.")
            return "No prompt found in .exegol/active_prompt.md"

        try:
            with open(prompt_file, 'r', encoding='utf-8') as f:
                raw_prompt = f.read()
            
            # --- SECURITY GUARD: Input Sanitization (sec_sec_arch_006) ---
            sanitization_result = sanitize_prompt(raw_prompt)
            active_prompt = sanitization_result["sanitized_text"]
            
            if sanitization_result["is_suspicious"]:
                print(f"[{self.name}] WARNING: {sanitization_result['warning']}")
                log_security_event(
                    actor=self.name,
                    action="input_sanitization_warning",
                    outcome="flagged",
                    repo_path=repo_path,
                    session_id=handoff.session_id,
                    details={
                        "warning": sanitization_result["warning"],
                        "prompt_snippet": raw_prompt[:100]
                    }
                )
            
            print(f"[{self.name}] Analyzing prompt: {active_prompt[:100]}...")

            if "prototype" in active_prompt.lower() or "sandbox" in active_prompt.lower():
                res = self._handle_sandbox_request(repo_path, active_prompt)
            else:
                # Real coding loop
                res = self._run_coding_loop(repo_path, active_prompt, handoff)
            
            duration = time.time() - start_time
            log_interaction(
                agent_id=self.name,
                outcome="success",
                task_summary=res[:200],
                repo_path=repo_path,
                steps_used=self._steps_used,
                duration_seconds=duration,
                session_id=handoff.session_id,
                state_changes={
                    "snapshot_hash": self.snapshot_hash,
                    "next_agent_id": getattr(self, "next_agent_id", None)
                }
            )
            return res
            
        except Exception as e:
            duration = time.time() - start_time
            log_interaction(
                agent_id=self.name,
                outcome="failure",
                task_summary=f"Error: {str(e)}",
                repo_path=repo_path,
                steps_used=self._steps_used,
                duration_seconds=duration,
                errors=[str(e)],
                session_id=handoff.session_id,
                state_changes={"snapshot_hash": self.snapshot_hash}
            )
            return f"[{self.name}] Error during execution: {e}"

    def _handle_sandbox_request(self, repo_path, active_prompt):
        print(f"[{self.name}] Prototyping request detected. Scaffolding sandbox...")
        app_id = "demo_app"  # In a real run, this would be parsed from the prompt or schema
        sandbox_path = create_sandbox(repo_path, app_id)
        
        # Deploy boilerplate with schema-compliant app.exegol.json
        files = {
            "index.html": "<h1>Hello from Exegol Sandbox</h1>",
            "app.js": "console.log('Sandbox app running');",
            "app.exegol.json": json.dumps({
                "app_name": "Demo Prototyped App",
                "version": "1.0.0",
                "architecture": {
                    "diagram_type": "mermaid",
                    "source": "README.md"
                },
                "inference": {
                    "provider": "ollama",
                    "base_model": "llama3"
                },
                "components": [
                    {
                        "name": "frontend",
                        "role": "frontend"
                    }
                ]
            }, indent=4)
        }
        deploy_to_sandbox(sandbox_path, files)
        self._steps_used += 1
        
        # Validate schema
        schema_path = os.path.join(repo_path, ".exegol", "schemas", "app_schema.json")
        validation = validate_app_schema(sandbox_path, schema_path)
        
        status_msg = f"Validation: {validation['status'].upper()} - {validation['message']}"
        print(f"[{self.name}] {status_msg}")
        
        return f"Experience Sandbox created at: {sandbox_path}. Prototype deployed. {status_msg}"

    def _run_coding_loop(self, repo_path, active_prompt, handoff):
        """Standard coding actions using LLM to plan and tools to execute.
        
        Actions from the LLM are validated through CodingAction before dispatch,
        preventing raw-dict runtime errors (arch_dex_integration_sync).
        """
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
        skipped = 0
        for action in actions:
            if self._steps_used >= self.max_steps:
                break

            # Validate and coerce action through CodingAction schema
            validated = _validate_action(action)
            if validated is None:
                skipped += 1
                continue

            # --- SECURITY GUARD: Path Boundary Check ---
            if not self._validate_action_path(repo_path, validated.path):
                print(f"[{self.name}] SECURITY: Rejected path traversal attempt: {validated.path}")
                log_security_event(
                    actor=self.name,
                    action="path_traversal_blocked",
                    outcome="blocked",
                    repo_path=repo_path,
                    session_id=handoff.session_id,
                    details={"attempted_path": validated.path}
                )
                results.append(f"REJECTED (path traversal blocked): {validated.path}")
                self._steps_used += 1
                continue

            file_path = os.path.join(repo_path, validated.path)

            if validated.type == "write":
                res = write_file(file_path, validated.content)
                results.append(f"Write {validated.path}: {res}")
            elif validated.type == "replace":
                res = replace_content(file_path, validated.target, validated.content)
                results.append(f"Replace in {validated.path}: {res}")

            self._steps_used += 1

        if skipped:
            print(f"[{self.name}] Skipped {skipped} malformed action(s) due to schema validation.")

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
