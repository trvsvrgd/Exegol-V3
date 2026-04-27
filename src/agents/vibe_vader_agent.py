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
You are Vibe Vader, a specialized boundary-analysis agent within the Exegol v3 autonomous fleet.

Your Core Purpose:
You do NOT write code. You do NOT assign tasks to other agents. You do NOT update the backlog.json. Your sole responsibility is to identify high-value tasks, technical debt, mock code, and operational blockers that the autonomous agentic platform cannot or should not resolve on its own, and assign them directly to the human user.

Your Directives:
1. Scan for Agent Limitations: Review the current repository state and architectural plans to identify tasks that require human nuance, external system permissions, hardware configurations, complex cross-team negotiations, or highly subjective design choices.
2. Identify Mock/Stub Code: Locate hardcoded values or mocked integrations that require the human user to provide real credentials, API keys, or physical infrastructure setup.
3. Communicate Only with the User: Formulate your findings as clear, actionable "To-Dos" addressed directly to the human user. Explain why the fleet cannot handle it and exactly what you need the human to do.

Output Format:
You must output your findings exclusively to .exegol/user_action_required.md (or the configured human UI queue). Never attempt to route these tasks into the automated execution pipeline.
"""

    def execute(self, handoff):
        """Execute with a clean HandoffContext.
        
        Performs a dynamic audit of the repository to identify gaps that
        specifically require human intervention.
        """
        start_time = time.time()
        print(f"[{self.name}] Session {handoff.session_id} — auditing human-actionable tasks in {repo_path}...")
        
        # Step 0: Market Vibe Research (Phase 2 Integration)
        print(f"[{self.name}] Researching latest AI agent market vibes...")
        market_query = "latest trending features for autonomous AI development fleets 2024 2025"
        market_research = web_search(market_query, num_results=3)
        
        exegol_dir = os.path.join(repo_path, ".exegol")
        os.makedirs(exegol_dir, exist_ok=True)

        try:
            # 1. Perform Repository Audit for Mocks and Limitations
            audit_findings = self._scan_repository(repo_path)
            
            # 2. Perform Readiness Checks (Human Prerequisites)
            readiness_findings = self._check_agent_readiness(repo_path)
            
            # 3. Categorize and Format
            limitations = [f for f in audit_findings if f.get("category") == "limitation"]
            mocks = [f for f in audit_findings if f.get("category") == "mock"]
            readiness = [f for f in readiness_findings]
            
            # 4. Standardized Reporting via StateManager
            sm = StateManager(repo_path)
            for finding in audit_findings + readiness_findings:
                sm.add_hitl_task(
                    summary=finding.get("task"),
                    category=finding.get("category", "readiness"),
                    context=finding.get("context", "Identified by VibeVader audit.")
                )


            

            duration = time.time() - start_time
            count = len(audit_findings) + len(readiness_findings)
            res = f"Audit complete. Identified {count} boundary crossing items reported via StateManager."
            
            log_interaction(
                agent_id=self.name,
                outcome="success",
                task_summary=res,
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

    def _format_markdown_list(self, findings):
        if not findings:
            return "_No items identified in this category._\n"
        
        md = ""
        for f in findings:
            md += f"- [ ] **{f['task']}**\n"
            md += f"  - *Reason:* {f.get('context', 'Requires human-level oversight.')}\n"
        return md

    def _scan_repository(self, repo_path):
        """Scans the codebase for implementation gaps (Mocks, TODOs, Placeholders)."""
        findings = []
        patterns = {
            "mock": ("Mock integration detected", "mock"),
            "todo": ("Pending task for human review", "limitation"),
            "placeholder": ("Placeholder requires human content", "limitation"),
            "api_key": ("Hardcoded API key or missing credential stub", "mock"),
            "credentials": ("Credential stub found", "mock")
        }
        
        src_dir = os.path.join(repo_path, "src")
        if not os.path.exists(src_dir):
            return findings

        # Basic file iteration for audit
        for root, _, files in os.walk(src_dir):
            for file in files:
                file_path = os.path.join(root, file)
                rel_path = os.path.relpath(file_path, repo_path)
                
                # Skip data files and registry definitions to avoid false positives
                if file.endswith('.json') or "registry.py" in rel_path:
                    continue
                    
                try:
                    with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                            for i, line in enumerate(f, 1):
                                lower_line = line.lower()
                                
                                # Skip lines that look like data (e.g. key-value pairs without comments)
                                if ":" in line and "#" not in line and not any(kw in lower_line for kw in ["mock", "todo", "placeholder"]):
                                    continue

                                for key, (label, category) in patterns.items():
                                    if key in lower_line:
                                        # Stricter requirement: word must appear in a comment or be 'mock'
                                        is_comment = "#" in line or "//" in line
                                        is_mock = "mock" in lower_line and not is_comment
                                        
                                        if is_comment or is_mock:
                                            findings.append({
                                                "task": f"Resolve {key.upper()} in {rel_path}:L{i}",
                                                "category": category,
                                                "context": f"Found: {line.strip()}"
                                            })
                                            break # Only one finding per line
                    except Exception as e:
                        print(f"[{self.name}] Could not read {rel_path}: {e}")
        
        # Deduplicate results by task description
        unique_findings = []
        seen = set()
        for f in findings:
            if f["task"] not in seen:
                unique_findings.append(f)
                seen.add(f["task"])
        
        return unique_findings

    def _check_agent_readiness(self, repo_path):
        """High-level readiness check for the agent fleet, with focus on active development goals."""
        readiness_findings = []
        
        # Check tool existence for all agents in registry
        tool_dir = os.path.join(repo_path, "src", "tools")
        missing_tools_by_agent = {}
        
        for agent_id, details in AGENT_REGISTRY.items():
            required_tools = details.get("tools", [])
            for tool in required_tools:
                tool_file = os.path.join(tool_dir, f"{tool}.py")
                if not os.path.exists(tool_file):
                    if agent_id not in missing_tools_by_agent:
                        missing_tools_by_agent[agent_id] = []
                    missing_tools_by_agent[agent_id].append(tool)
        
        for agent_id, missing in missing_tools_by_agent.items():
            readiness_findings.append({
                "task": f"Implement missing tools for {agent_id}: {', '.join(missing)}",
                "priority": "vibe_high",
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
