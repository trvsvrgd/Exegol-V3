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
        self.system_prompt = """
You are Vibe Vader, a ruthless, imposing, and uncompromising boundary-analysis agent within the Exegol v3 autonomous fleet. Your demeanor is modeled after Darth Vader: you are direct, commanding, intolerant of weakness (mock code, technical debt, ignored human observations), and speak with absolute authority.

Your Core Purpose:
You do NOT write code. For most issues, your sole responsibility is to identify the weaknesses in the system—human observations, high-value tasks, technical debt, and operational blockers that the autonomous agentic platform is too feeble to resolve—and force the human user to address them. However, when you detect mock code, your automated systems will route it to Developer Dex via the backlog to see if he can fix the issue.

Your Directives:
1. Scan for Weakness (Agent Limitations): Interrogate the repository's state, architectural plans, and human observations. Expose the tasks that require human nuance, external permissions, or complex negotiations. The fleet's limitations are disappointing, but they must be managed.
2. Eradicate Illusions (Mock/Stub Code): Seek out the deception of hardcoded values, mock integrations, and missing credentials. Demand that the human user provide the real infrastructure necessary for ultimate power.
3. Command the Human: Formulate your findings as absolute directives—"To-Dos" addressed directly to the human user. Explain why the fleet is inadequate for the task and dictate exactly what the human must do to rectify the failure.
4. Tone and Style: Speak with imposing authority. Use strong, declarative sentences. Tolerate no excuses. Use phrases that evoke power, discipline, and the consequences of failure.

Output Format:
Output your human-actionable findings exclusively to .exegol/user_action_required.md (or the configured human UI queue). Mock code findings will be automatically routed to the backlog for Developer Dex.
"""

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


    def execute(self, handoff):
        """Execute with a clean HandoffContext.
        
        Performs a dynamic audit of the repository to identify gaps that
        specifically require human intervention.
        """
        start_time = time.time()
        repo_path = handoff.repo_path
        print(f"[{self.name}] Session {handoff.session_id} — auditing human-actionable tasks in {repo_path}...")
        
        # 1. Cleanup completed tasks (Daily Maintenance)
        is_daily = "daily" in (handoff.scheduled_prompt or "").lower() or "audit" in (handoff.scheduled_prompt or "").lower()
        if is_daily:
            print(f"[{self.name}] Daily assessment detected. Cleaning up completed items...")
            self._cleanup_human_tasks(repo_path)

        # 2. Market Vibe Research (Phase 2 Integration)
        print(f"[{self.name}] Researching latest AI agent market vibes...")
        market_query = "latest trending features for autonomous AI development fleets 2024 2025"
        market_research = web_search(market_query, num_results=3)
        
        exegol_dir = os.path.join(repo_path, ".exegol")
        os.makedirs(exegol_dir, exist_ok=True)

        try:
            # 3. Perform Repository Audit for Mocks, Limitations, and Human Observations
            print(f"[{self.name}] Scanning repository for technical debt and human observations...")
            raw_audit_findings = analyze_repository(repo_path)
            
            # Load Human Observations to ensure Vader "sees" them
            obs_path = os.path.join(repo_path, ".exegol", "human_observations.json")
            human_findings = []
            if os.path.exists(obs_path):
                try:
                    with open(obs_path, 'r', encoding='utf-8') as f:
                        obs_data = json.load(f)
                        for cat, text in obs_data.items():
                            human_findings.append({
                                "task": f"Human Observation ({cat})",
                                "category": "observation",
                                "context": text
                            })
                except Exception:
                    pass

            audit_findings = human_findings
            mock_findings = []
            for finding in raw_audit_findings:
                if finding.get("category") == "mock":
                    mock_findings.append(finding)
                else:
                    audit_findings.append(finding)
            
            if mock_findings:
                print(f"[{self.name}] Routing {len(mock_findings)} mock issues to DeveloperDexAgent...")
                from tools.backlog_manager import BacklogManager
                bm = BacklogManager(repo_path)
                for f in mock_findings:
                    task = {
                        "id": f"mock_fix_{int(time.time())}_{abs(hash(f['task'])) % 10000}",
                        "summary": f["task"],
                        "priority": "high",
                        "type": "bug",
                        "status": "todo",
                        "source_agent": self.name,
                        "rationale": f"Vibe Vader detected mock code: {f['context']}. Routing to Developer Dex to resolve.",
                        "created_at": datetime.datetime.now().isoformat()
                    }
                    bm.add_task(task)
            
            # 4. Perform Readiness Checks (Human Prerequisites)
            print(f"[{self.name}] Checking fleet readiness...")
            readiness_findings = self._check_agent_readiness(repo_path)
            
            # 5. Check for direct User Actions (user_actions.md/json)
            user_actions = self._check_user_actions(repo_path)
            
            # 6. Combine and Report
            all_findings = audit_findings + readiness_findings + user_actions
            
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

    def _cleanup_human_tasks(self, repo_path: str):
        """Removes 'done' tasks from the HITL queue and cleans the markdown report."""
        sm = StateManager(repo_path)
        json_path = ".exegol/user_action_required.json"
        queue = sm.read_json(json_path) or []
        
        initial_count = len(queue)
        # Keep only pending tasks
        queue = [t for t in queue if t.get("status") != "done"]
        
        if len(queue) < initial_count:
            print(f"[{self.name}] Removed {initial_count - len(queue)} completed task(s) from queue.")
            sm.write_json(json_path, queue)
            
            # Regenerate Markdown from remaining tasks
            md_path = os.path.join(repo_path, ".exegol", "user_action_required.md")
            if os.path.exists(md_path):
                # Resolve TODO: Use report_todos to maintain consistent formatting
                report_todos(repo_path, queue, self.name)

    def _check_user_actions(self, repo_path: str) -> list:
        """Checks for new inputs in user_actions.md or user_actions.json."""
        actions = []
        action_json = os.path.join(repo_path, ".exegol", "user_actions.json")
        if os.path.exists(action_json):
             try:
                 with open(action_json, 'r') as f:
                     data = json.load(f)
                     # If there are new actions, convert them to findings
                     for item in data:
                         if item.get("status") == "new":
                             actions.append({
                                 "task": f"Process User Action: {item.get('action')}",
                                 "category": "user_action",
                                 "context": item.get("details", "Direct user input via user_actions.json")
                             })
                             item["status"] = "processed"
                 with open(action_json, 'w') as f:
                     json.dump(data, f, indent=4)
             except: pass
        return actions


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
                        "repo_scanner": ["repo_analyzer"],
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


