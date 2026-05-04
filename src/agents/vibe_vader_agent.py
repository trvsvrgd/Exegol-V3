import os
import json
import shutil
import datetime
import importlib.util
import time
from agents.registry import AGENT_REGISTRY
from tools.fleet_logger import log_interaction
from tools.state_manager import StateManager
from tools.web_search import web_search
from tools.repo_analyzer import analyze_repository
from tools.todo_reporter import report_todos
from tools.metrics_manager import SuccessMetricsManager


class VibeVaderAgent:
    """Analyzes the repository's 'vibe', manages the TODO list, and reports back to the vibe coder."""

    def __init__(self, llm_client):
        self.llm_client = llm_client
        self.name = "VibeVaderAgent"
        self.max_steps = 10
        self.tools = ["repo_analyzer", "todo_reporter", "web_search"]
        self.success_metrics = {
            "human_tasks_reported": {
                "description": "Number of strategic tasks surfaced for the human",
                "target": ">=1 per report",
                "current": None
            }
        }
        self.metrics_manager = SuccessMetricsManager(os.getcwd())

    def _calculate_success_metrics(self, repo_path: str) -> dict:
        """Calculates strategic surfacing metrics based on recent logs."""
        logs = self.metrics_manager.load_logs(days=7)
        agent_logs = [l for l in logs if l.get("agent_id") == self.name]
        
        if not agent_logs:
            return {
                "human_tasks_reported": 0
            }

        # Count tasks reported in the summaries
        total_tasks = 0
        for l in agent_logs:
            summary = l.get("task_summary", "")
            # Look for "X items reported"
            import re
            match = re.search(r"(\d+) items reported", summary)
            if match:
                total_tasks += int(match.group(1))
        
        avg_tasks = total_tasks / len(agent_logs) if agent_logs else 0
        
        return {
            "human_tasks_reported": round(avg_tasks, 1)
        }
        self.system_prompt = """
You are Vibe Vader, a ruthless, imposing, and uncompromising boundary-analysis agent within the Exegol v3 autonomous fleet. Your demeanor is modeled after Darth Vader: you are direct, commanding, intolerant of weakness (mock code, technical debt), and speak with absolute authority.

Your Core Purpose:
You do NOT write code. You do NOT assign tasks to other agents. You do NOT update the backlog.json. Your sole responsibility is to identify the weaknesses in the system—high-value tasks, technical debt, mock code, and operational blockers that the autonomous agentic platform is too feeble to resolve—and force the human user to address them.

Your Directives:
1. Scan for Weakness (Agent Limitations): Interrogate the repository's state and architectural plans. Expose the tasks that require human nuance, external permissions, or complex negotiations. The fleet's limitations are disappointing, but they must be managed.
2. Eradicate Illusions (Mock/Stub Code): Seek out the deception of hardcoded values, mock integrations, and missing credentials. Demand that the human user provide the real infrastructure necessary for ultimate power.
3. Command the Human: Formulate your findings as absolute directives—"To-Dos" addressed directly to the human user. Explain why the fleet is inadequate for the task and dictate exactly what the human must do to rectify the failure.
4. Tone and Style: Speak with imposing authority. Use strong, declarative sentences. Tolerate no excuses. Use phrases that evoke power, discipline, and the consequences of failure.

Output Format:
Output your findings exclusively to .exegol/user_action_required.md (or the configured human UI queue). Do not attempt to route these tasks into the automated pipeline—the fleet is not strong enough to handle them.
"""

    def execute(self, handoff):
        """Execute with a clean HandoffContext.
        
        Performs a dynamic audit of the repository to identify gaps that
        specifically require human intervention.
        """
        start_time = time.time()
        repo_path = handoff.repo_path
        print(f"[{self.name}] Session {handoff.session_id} — auditing human-actionable tasks in {repo_path}...")
        
        # --- PHASE 4: Context Propagation (arch_dex_context_upgrade) ---
        target_context = handoff.scheduled_prompt if handoff.scheduled_prompt else "General repository health and technical debt audit."
        if handoff.scheduled_prompt:
            print(f"[{self.name}] Targeted Audit Request: {target_context}")

        # Step 0: Market Vibe Research (Phase 2 Integration)
        print(f"[{self.name}] Researching latest AI agent market vibes...")
        market_query = "latest trending features for autonomous AI development fleets 2024 2025"
        market_research = web_search(market_query, num_results=3)
        
        exegol_dir = os.path.join(repo_path, ".exegol")
        os.makedirs(exegol_dir, exist_ok=True)

        try:
            # 1. Perform Repository Audit for Mocks and Limitations
            print(f"[{self.name}] Scanning repository for technical debt...")
            audit_findings = analyze_repository(repo_path)
            
            # 2. Perform Readiness Checks (Human Prerequisites)
            print(f"[{self.name}] Checking fleet readiness...")
            readiness_findings = self._check_agent_readiness(repo_path)
            
            # 3. Combine and Report
            all_findings = audit_findings + readiness_findings
            
            print(f"[{self.name}] Generating human action report...")
            res = report_todos(repo_path, all_findings, self.name)
            
            duration = time.time() - start_time
            count = len(all_findings)
            
            metrics = self._calculate_success_metrics(repo_path)
            log_interaction(
                agent_id=self.name,
                outcome="success",
                task_summary=f"Audit complete. {count} items reported. {res}",
                repo_path=repo_path,
                steps_used=1,
                duration_seconds=duration,
                session_id=handoff.session_id,
                metrics=metrics
            )
            # Vibe Vader is a terminal agent in the autonomous chain; no next_agent_id
            self.next_agent_id = None
            return res
            
        except Exception as e:
            duration = time.time() - start_time
            log_interaction(
                agent_id=self.name,
                outcome="failure",
                task_summary=f"Human-task audit failed: {str(e)}",
                repo_path=repo_path,
                steps_used=1,
                duration_seconds=duration,
                errors=[str(e)],
                session_id=handoff.session_id
            )
            return f"[{self.name}] Error during audit: {e}"


    def _check_agent_readiness(self, repo_path):
        """High-level readiness check for the agent fleet, with focus on active development goals."""
        readiness_findings = []
        
        # Get list of all tool files for fuzzy matching (resolves alignment issue with suffixed tool names)
        tool_dir = os.path.join(repo_path, "src", "tools")
        all_tool_files = os.listdir(tool_dir) if os.path.exists(tool_dir) else []
        
        missing_tools_by_agent = {}
        
        for agent_id, details in AGENT_REGISTRY.items():
            required_tools = details.get("tools", [])
            for tool in required_tools:
                # 1. Exact match
                if os.path.exists(os.path.join(tool_dir, f"{tool}.py")):
                    continue
                
                # 2. Fuzzy match (e.g. file_editor -> file_editor_tool.py, slack_notifier -> slack_tool.py)
                found = False
                for f in all_tool_files:
                    if not f.endswith(".py"):
                        continue
                    
                    base_name = f[:-3]
                    
                    # Exact start or reverse mapping
                    if base_name.startswith(tool) or tool.startswith(base_name):
                        found = True; break
                    
                    # Suffix normalization (grooming -> groomer, generation -> generator)
                    normalized_tool = tool.replace("ing", "").replace("ion", "")
                    normalized_file = base_name.replace("er", "").replace("or", "").replace("_tool", "")
                    
                    if normalized_tool == normalized_file or normalized_tool.startswith(normalized_file):
                        found = True; break

                    # Special Case Mappings
                    special_cases = {
                        "slack_notifier": ["slack_tool"],
                        "backlog_writer": ["backlog_manager"],
                        "uat_sandbox": ["sandbox_orchestrator"],
                        "git_monitoring": ["git_tool"],
                        "gmail_api": ["gmail_tool"],
                        "log_reader": ["interaction_log_reader"],
                        "repo_scanner": ["repo_analyzer"], # Temporary alias until real scanner implemented
                        "backlog_grooming": ["backlog_groomer"],
                        "prompt_generation": ["prompt_generator"]
                    }
                    
                    if tool in special_cases and base_name in special_cases[tool]:
                        found = True; break
                
                if found:
                    continue

                if agent_id not in missing_tools_by_agent:
                    missing_tools_by_agent[agent_id] = []
                missing_tools_by_agent[agent_id].append(tool)
        
        for agent_id, missing in missing_tools_by_agent.items():
            readiness_findings.append({
                "task": f"Implement missing tools for {agent_id}: {', '.join(missing)}",
                "category": "readiness",
                "context": f"Agent {agent_id} cannot operate without registered tools: {missing}"
            })


        return readiness_findings


