import os
import json
import shutil
import importlib.util
from agents.registry import AGENT_REGISTRY


class VibeVaderAgent:
    """Analyzes the repository's 'vibe', manages the TODO list, and reports back to the vibe coder."""

    def __init__(self, llm_client):
        self.llm_client = llm_client
        self.name = "VibeVaderAgent"
        self.max_steps = 10
        self.tools = ["repo_analyzer", "todo_reporter"]
        self.success_metrics = {
            "human_tasks_reported": {
                "description": "Number of strategic tasks surfaced for the human",
                "target": ">=1 per report",
                "current": None
            }
        }
        self.system_prompt = self.llm_client.generate_system_prompt(self)

    def execute(self, handoff):
        """Execute with a clean HandoffContext.
        
        Performs a dynamic audit of the repository to identify mocks, placeholders,
        and TODOs that depend on human interaction to complete.
        """
        repo_path = handoff.repo_path
        print(f"[{self.name}] Session {handoff.session_id} — auditing tasks for the vibe coder in {repo_path}...")
        
        exegol_dir = os.path.join(repo_path, ".exegol")
        os.makedirs(exegol_dir, exist_ok=True)
        todo_file = os.path.join(exegol_dir, "vibe_todo.json")

        # 1. Load existing TODOs
        todo_list = []
        if os.path.exists(todo_file):
            try:
                with open(todo_file, 'r', encoding='utf-8') as f:
                    todo_list = json.load(f)
            except Exception as e:
                print(f"[{self.name}] Error reading vibe_todo: {e}")

        # 2. Perform Repository Audit
        audit_findings = self._scan_repository(repo_path)
        
        # 3. Perform Readiness Checks for Agent Readiness
        readiness_findings = self._check_agent_readiness(repo_path)
        
        # 4. Combine with Strategic Vibe Tasks
        strategic_tasks = [
            {"task": "Review recent agent trajectories and verify the 'vibe' matches project intent", "priority": "vibe_high"},
            {"task": "Define the next architectural pivot for the autonomous loop", "priority": "vibe_critical"},
            {"task": "Sync with the team on Slack regarding recent autonomous milestones", "priority": "vibe_medium"}
        ]
        
        all_potential_tasks = audit_findings + readiness_findings + strategic_tasks
        
        # 4. Update the list with new findings
        added_count = 0
        current_task_descs = [t.get("task") for t in todo_list]
        
        for p_task in all_potential_tasks:
            desc = p_task["task"]
            if desc not in current_task_descs:
                new_task = {
                    "id": f"vibe_{len(todo_list)+1:03d}",
                    "task": desc,
                    "priority": p_task.get("priority", "vibe_low"),
                    "status": "waiting_for_human",
                    "source": self.name,
                    "context": p_task.get("context", "General project health")
                }
                todo_list.append(new_task)
                print(f"[{self.name}] Identified task: {desc}")
                added_count += 1
                
        # 5. Write back to vibe_todo.json
        with open(todo_file, 'w', encoding='utf-8') as f:
            json.dump(todo_list, f, indent=4)

        if added_count > 0:
            return f"Audit complete. Identified {added_count} new implementation gaps requiring your attention in {todo_file}."
        else:
            return f"Audit complete. No new implementation gaps identified. Vibe remains solid."

    def _scan_repository(self, repo_path):
        """Scans the codebase for implementation gaps (Mocks, TODOs, Placeholders)."""
        findings = []
        patterns = {
            "mock": "Mock implementation detected - requires real integration",
            "todo": "Pending task identified in source code",
            "fixme": "Bug or technical debt needing attention",
            "placeholder": "Generic placeholder needing specific content"
        }
        
        src_dir = os.path.join(repo_path, "src")
        if not os.path.exists(src_dir):
            return findings

        # Basic file iteration for audit
        for root, _, files in os.walk(src_dir):
            for file in files:
                if file.endswith(('.py', '.js', '.md', '.html', '.css')):
                    file_path = os.path.join(root, file)
                    rel_path = os.path.relpath(file_path, repo_path)
                    
                    # Skip self to avoid meta-placeholder loops
                    if "vibe_vader_agent" in rel_path:
                        continue
                    
                    try:
                        with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                            for i, line in enumerate(f, 1):
                                lower_line = line.lower()
                                for key, label in patterns.items():
                                    if key in lower_line:
                                        # Simple heuristic: if it's a comment or log string
                                        if "#" in line or 'mock' in lower_line or 'todo' in lower_line:
                                            findings.append({
                                                "task": f"Resolve {key.upper()} in {rel_path}:L{i}",
                                                "priority": "vibe_critical" if "mock" in key else "vibe_medium",
                                                "context": f"Found: {line.strip()}"
                                            })
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
