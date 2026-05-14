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
from tools.web_search import web_search
from tools.slack_tool import post_to_slack
from tools.agentic_coding import execute_coding_task
from tools.metrics_manager import SuccessMetricsManager
from tools.heartbeat_monitor import HeartbeatMonitor

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
        self.tools = ["file_editor", "slack_notifier", "agentic_coding", "sandbox_orchestrator", "web_search"]
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
        self.metrics_manager = SuccessMetricsManager(os.getcwd())
        self.system_prompt = self.llm_client.generate_system_prompt(self)

        self.system_prompt += "\n\nCRITICAL: After completing any coding task or sandbox creation, you MUST hand off to QualityQuigonAgent for validation. Set your next_agent_id to 'quality_quigon'."

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

        # --- PHASE 4: Context Propagation (arch_dex_context_upgrade) ---
        raw_prompt = ""
        prompt_path = os.path.join(repo_path, ".exegol", "active_prompt.md")
        
        if os.path.exists(prompt_path):
            with open(prompt_path, 'r', encoding='utf-8') as f:
                raw_prompt = f.read()

        # If we have a scheduled prompt (e.g. from Slack wake-word), it takes priority
        # or appends to the existing groomed prompt.
        if handoff.scheduled_prompt:
            if raw_prompt:
                print(f"[{self.name}] Merging scheduled prompt with active_prompt.md context.")
                raw_prompt = f"USER CONTEXT / DIRECTIVE:\n{handoff.scheduled_prompt}\n\nBACKGROUND TASK:\n{raw_prompt}"
            else:
                print(f"[{self.name}] Using scheduled prompt: {handoff.scheduled_prompt}")
                raw_prompt = handoff.scheduled_prompt

        if not raw_prompt:
            print(f"[{self.name}] No active prompt or scheduled context found.")
            return "No actionable prompt found in .exegol/active_prompt.md or handoff context."

        try:
            # --- SECURITY GUARD: Input Sanitization (sec_sec_arch_006) ---
            sanitization_result = sanitize_prompt(raw_prompt)
            active_prompt = sanitization_result["sanitized_text"]
            
            if sanitization_result["is_suspicious"]:
                warning_msg = f"SECURITY ALERT: Suspicious prompt pattern detected in session {handoff.session_id}."
                print(f"[{self.name}] {warning_msg}")
                
                # Log security event
                log_security_event(
                    actor=self.name,
                    action="input_sanitization_blocked",
                    outcome="blocked",
                    repo_path=repo_path,
                    session_id=handoff.session_id,
                    details={
                        "warning": sanitization_result["warning"],
                        "prompt_snippet": raw_prompt[:200]
                    }
                )
                
                # Notify Slack with a block message (arch_dex_slack_integration)
                slack_msg = f"🚨 *SECURITY BLOCK* 🚨\n{warning_msg}\n*Prompt:* `{raw_prompt[:100]}...`\nManual review required."
                post_to_slack(slack_msg)
                
                return f"Execution blocked due to security concerns: {sanitization_result['warning']}. Awaiting manual review."

            if "prototype" in active_prompt.lower() or "sandbox" in active_prompt.lower():
                res = self._handle_sandbox_request(repo_path, active_prompt)
            else:
                # Pulse heartbeat for long coding loops (arch_agent_heartbeat)
                HeartbeatMonitor.pulse_session(repo_path, handoff.session_id)
                # Real coding loop
                res = self._run_coding_loop(repo_path, active_prompt, handoff)
            
            # --- PHASE 3: Update Success Metrics ---
            current_metrics = self._calculate_success_metrics(repo_path)
            
            # Notify Slack (arch_dex_slack_integration)
            self._notify_completion(handoff.session_id, res)
            
            # Ensure handoff to Quigon
            self.next_agent_id = "quality_quigon"
            
            # Determine outcome based on results
            outcome = "success"
            if "Error" in res or "Failed to parse" in res or "0 actions performed" in res:
                outcome = "failure"
                
            duration = time.time() - start_time

            log_interaction(
                agent_id=self.name,
                outcome=outcome,
                task_summary=res[:200],
                repo_path=repo_path,
                steps_used=self._steps_used,
                duration_seconds=duration,
                session_id=handoff.session_id,
                state_changes={
                    "snapshot_hash": self.snapshot_hash,
                    "next_agent_id": getattr(self, "next_agent_id", None)
                },
                metrics=current_metrics
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
        
        # Dynamically parse app_id from prompt or fallback to a timestamped demo
        import re
        match = re.search(r'app(?:_id|name)[\s=:]*([a-zA-Z0-9_-]+)', active_prompt, re.IGNORECASE)
        app_id = match.group(1) if match else f"app_{int(time.time())}"

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
        # Use the high-level agentic_coding tool
        res_data = execute_coding_task(
            task_description=active_prompt,
            repo_path=repo_path,
            llm_client=self.llm_client,
            agent_name=self.name,
            system_prompt=self.system_prompt,
            max_steps=self.max_steps,
            session_id=handoff.session_id
        )
        
        # res_data is now a dict: {"summary": ..., "actions": ..., "results": ...}
        res = res_data.get("summary", "No summary returned.")
        actions = res_data.get("actions", [])
        results = res_data.get("results", [])
        
        # --- TASK: Implementation Plan Logging (doc_implementation_plan_logging) ---
        self._log_implementation_plan(repo_path, actions, results, active_prompt)
        
        # Capture snapshot for regression testing (poe_009)
        snapshot_data = {
            "task_id": getattr(handoff, "task_id", "unknown"),
            "agent": self.name,
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

    def _calculate_success_metrics(self, repo_path: str) -> dict:
        """Calculates real-time performance metrics for DeveloperDex."""
        metrics = {
            "sandbox_acceptance_rate": 0.0,
            "bugs_found_in_qa": 0,
            "avg_prompts_to_acceptance": 0.0
        }
        
        try:
            from tools.fleet_logger import read_interaction_logs
            logs = read_interaction_logs([repo_path], days=7)
            
            # 1. Sandbox Acceptance Rate
            sandbox_sessions = [l for l in logs if "sandbox" in l.get("task_summary", "").lower() and l.get("agent_id") == self.name]
            if sandbox_sessions:
                sandbox_session_ids = {l.get("session_id") for l in sandbox_sessions if l.get("session_id")}
                approved = [l for l in logs if l.get("agent_id") == "QualityQuigonAgent" and l.get("outcome") == "success" and l.get("session_id") in sandbox_session_ids]
                metrics["sandbox_acceptance_rate"] = round(len(approved) / len(sandbox_sessions), 2) if len(sandbox_sessions) > 0 else 1.0
            
            # 2. Bugs found in QA
            quigon_logs = [l for l in logs if l.get("agent_id") == "QualityQuigonAgent"]
            bugs = 0
            for ql in quigon_logs:
                # If Quigon reported errors or failures, and we were the previous agent (session link)
                if ql.get("outcome") == "failure" or len(ql.get("errors", [])) > 0:
                    bugs += 1
            metrics["bugs_found_in_qa"] = bugs
            
            # 3. Avg prompts to acceptance
            dex_logs = [l for l in logs if l.get("agent_id") == self.name]
            if dex_logs:
                sessions = {}
                for l in dex_logs:
                    sid = l.get("session_id", "unknown")
                    sessions[sid] = sessions.get(sid, 0) + 1
                
                total_prompts = sum(sessions.values())
                metrics["avg_prompts_to_acceptance"] = round(total_prompts / len(sessions), 1) if sessions else 0.0
                
        except Exception as e:
            print(f"[{self.name}] Error calculating success metrics: {e}")
            
        return metrics

    def _log_implementation_plan(self, repo_path: str, actions: list, results: list, prompt: str):
        """Logs a human-readable implementation plan for the user to review."""
        logs_dir = os.path.join(repo_path, ".exegol", "interaction_logs")
        os.makedirs(logs_dir, exist_ok=True)
        
        timestamp = time.strftime("%Y%m%d_%H%M%S")
        plan_path = os.path.join(logs_dir, f"plan_dex_{timestamp}.md")
        
        plan_content = f"# Implementation Plan: DeveloperDex\n"
        plan_content += f"**Timestamp:** {time.ctime()}\n"
        plan_content += f"**Task Prompt:** {prompt}\n\n"
        plan_content += f"## Proposed Actions\n"
        
        for i, action in enumerate(actions):
            plan_content += f"### {i+1}. {action.get('type', 'Unknown').capitalize()}: `{action.get('path')}`\n"
            if action.get('type') == 'replace':
                plan_content += f"- **Target:** `{action.get('target')}`\n"
            plan_content += f"```\n{action.get('content')}\n```\n\n"
            
        plan_content += f"## Execution Results\n"
        for result in results:
            plan_content += f"- {result}\n"
            
        try:
            with open(plan_path, 'w', encoding='utf-8') as f:
                f.write(plan_content)
            print(f"[{self.name}] Implementation plan logged to {plan_path}")
        except Exception as e:
            print(f"[{self.name}] Failed to log implementation plan: {e}")

    def _notify_completion(self, session_id: str, summary: str):
        """Sends a completion notification to Slack."""
        message = f"✅ *{self.name}* completed task in session `{session_id}`\n"
        message += f"**Summary:** {summary[:500]}..."
        post_to_slack(message)

