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
            
            log_interaction(
                agent_id=self.name,
                outcome="success",
                task_summary=f"Audit complete. {count} items reported. {res}",
                repo_path=repo_path,
                steps_used=1,
                duration_seconds=duration,
                session_id=handoff.session_id
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
                    if f.startswith(tool) and f.endswith(".py"):
                        found = True; break
                    # Special Case Mappings
                    if tool == "slack_notifier" and "slack_tool.py" in all_tool_files:
                        found = True; break
                    if tool == "backlog_writer" and "backlog_manager.py" in all_tool_files:
                        found = True; break
                    if tool == "uat_sandbox" and "sandbox_orchestrator.py" in all_tool_files:
                        found = True; break
                    if tool == "git_monitoring" and "git_tool.py" in all_tool_files:
                        found = True; break
                    if tool == "gmail_api" and "gmail_tool.py" in all_tool_files:
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

        # Specific check for Cameraman Cassian video capabilities
        if "cameraman_cassian" in AGENT_REGISTRY:
            cassian_tasks = self._check_cassian_readiness(repo_path)
            readiness_findings.extend(cassian_tasks)
            
        return readiness_findings

    def _check_cassian_readiness(self, repo_path):
        """Specifically audits for video recording capabilities."""
        findings = []
        
        # 1. Check Playwright
        if not importlib.util.find_spec("playwright"):
            findings.append({
                "task": "Install Playwright in the environment (`pip install playwright` and `playwright install`)",
                "priority": "vibe_critical",
                "context": "CameramanCassianAgent requires playwright for screen recording."
            })
            
        # 2. Check FFmpeg
        if not shutil.which("ffmpeg"):
            findings.append({
                "task": "Install FFmpeg and ensure it is in the system PATH",
                "priority": "vibe_critical",
                "context": "CameramanCassianAgent requires FFmpeg for video clipping and processing."
            })
            
        # 3. Check requirements.txt
        req_path = os.path.join(repo_path, "requirements.txt")
        if os.path.exists(req_path):
            with open(req_path, 'r', encoding='utf-8') as f:
                content = f.read()
                if "playwright" not in content.lower():
                    findings.append({
                        "task": "Add `playwright` to requirements.txt",
                        "priority": "vibe_medium",
                        "context": "Keep the project dependencies synchronized."
                    })

        return findings
