import os
import time
import json
from tools.file_editor_tool import read_file, write_file, replace_content
from tools.readme_parser import ReadmeParser
from tools.diagram_generator import DiagramGenerator
from tools.slack_tool import post_to_slack
from tools.fleet_logger import log_interaction

class TechnicalTarkinAgent:
    """The Grand Moff of Documentation. 
    
    Responsible for creating 'awesome' READMEs, technical user guides, and 
    detailed breakdowns of complex capabilities like auditing and compliance.
    """

    def __init__(self, llm_client):
        self.llm_client = llm_client
        self.name = "TechnicalTarkinAgent"
        self.max_steps = 15
        self._steps_used = 0
        self.tools = ["file_editor", "readme_parser", "diagram_generator", "slack_notifier", "web_search", "interaction_log_reader"]
        self.success_metrics = {
            "documentation_coverage": {
                "description": "Percentage of core modules with dedicated technical guides",
                "target": ">=90%",
                "current": None
            },
            "readme_visual_score": {
                "description": "Qualitative score of README aesthetics (includes diagrams/videos)",
                "target": "Awesome",
                "current": None
            },
            "compliance_transparency": {
                "description": "Availability of detailed auditing and compliance breakdowns",
                "target": "Complete",
                "current": None
            }
        }
        self.system_prompt = self.llm_client.generate_system_prompt(self)
        self.system_prompt += "\n\nCRITICAL: Your documentation must be 'awesome'. Use Mermaid diagrams, rich formatting, and clear hierarchies. Do not just list features; explain the 'why' and 'how' with technical depth."

    def execute(self, handoff):
        """Execute the documentation mission."""
        start_time = time.time()
        self._steps_used = 0
        repo_path = handoff.repo_path
        print(f"[{self.name}] Session {handoff.session_id} — The Documentation Fleet is under my command.")

        # 1. Check for work in the previous week
        from tools.git_tool import has_commits_since
        from tools.log_reader import read_interaction_logs
        
        has_new_commits = has_commits_since(repo_path, timeframe="1 week ago")
        recent_logs = read_interaction_logs(repo_path, limit=50) # Assuming limit covers the week for a simple check
        
        if not has_new_commits and not recent_logs:
            print(f"[{self.name}] No new commits or interaction logs found for the previous week. Standing down.")
            return "No work detected in the previous week. Documentation is up to date."
        
        print(f"[{self.name}] Activity detected. Analyzing work history to update documentation...")

        # 1. Read the active prompt or task description
        prompt_file = os.path.join(repo_path, ".exegol", "active_prompt.md")
        active_task = ""
        if os.path.exists(prompt_file):
            with open(prompt_file, 'r', encoding='utf-8') as f:
                active_task = f.read()
        
        if not active_task:
            active_task = getattr(handoff, "task_description", "General documentation audit and enhancement.")

        print(f"[{self.name}] Mission Objective: {active_task[:100]}...")

        # 2. Analyze repository for auditing and compliance capabilities (if requested)
        compliance_data = {}
        if "compliance" in active_task.lower() or "audit" in active_task.lower():
            compliance_data = self._analyze_compliance_capabilities(repo_path)

        # 3. Plan and Execute Documentation Updates
        planning_prompt = f"""
        User Mission: {active_task}
        
        Repository Compliance Context: {json.dumps(compliance_data, indent=2)}
        
        Identify the documentation files to create or update. 
        - README.md should be 'awesome' with visuals (Mermaid diagrams).
        - Technical guides should be detailed and live in a 'docs/' directory.
        - Compliance breakdowns should be deep technical dives.

        Return a JSON list of actions:
        {{
            "actions": [
                {{
                    "type": "write" | "replace",
                    "path": "path/to/file.md",
                    "content": "Full markdown content",
                    "description": "Why this change is awesome"
                }}
            ]
        }}
        """

        response = self.llm_client.generate(planning_prompt, system_instruction=self.system_prompt, json_format=True)
        plan = self.llm_client.parse_json_response(response)

        results = []
        if plan and "actions" in plan:
            for action in plan["actions"]:
                if self._steps_used >= self.max_steps:
                    break
                
                file_path = os.path.join(repo_path, action["path"])
                os.makedirs(os.path.dirname(file_path), exist_ok=True)

                if action["type"] == "write":
                    res = write_file(file_path, action["content"])
                    results.append(f"Created/Updated {action['path']}: {res}")
                elif action["type"] == "replace":
                    # This would require a target string, for simplicity in this agent 
                    # we often overwrite or use specific markers
                    res = write_file(file_path, action["content"]) # Fallback to write for now
                    results.append(f"Overwrote {action['path']} with enhanced version.")
                
                self._steps_used += 1

        # 4. Notify Slack
        notification = f"📢 *TechnicalTarkinAgent Update*\n\nMission accomplished. Documentation fleet updated.\n"
        for res in results:
            notification += f"- {res}\n"
        post_to_slack(notification)

        duration = time.time() - start_time
        
        # Calculate success metrics before logging
        metrics = self._calculate_success_metrics(repo_path)
        
        log_interaction(
            agent_id=self.name,
            outcome="success",
            task_summary=f"Documentation update complete: {len(results)} files processed.",
            repo_path=repo_path,
            steps_used=self._steps_used,
            duration_seconds=duration,
            session_id=handoff.session_id,
            metrics=metrics
        )

        return f"Mission complete. Results:\n" + "\n".join(results)

    def _calculate_success_metrics(self, repo_path: str) -> dict:
        """Calculates documentation quality metrics."""
        metrics = {
            "documentation_coverage": 0.0,
            "readme_visual_score": 0.0,
            "compliance_transparency": 0.0
        }
        
        # 1. Documentation Coverage
        src_dir = os.path.join(repo_path, "src")
        python_files = []
        for root, _, files in os.walk(src_dir):
            for f in files:
                if f.endswith(".py") and "__init__" not in f:
                    python_files.append(f)
        
        if python_files:
            docs_dir = os.path.join(repo_path, "docs")
            documented_files = 0
            readme_content = ""
            readme_path = os.path.join(repo_path, "README.md")
            if os.path.exists(readme_path):
                with open(readme_path, 'r', encoding='utf-8') as f:
                    readme_content = f.read()
            
            for py_file in python_files:
                base_name = py_file.replace(".py", "")
                # Check in docs/
                doc_found = False
                if os.path.exists(docs_dir):
                    for df in os.listdir(docs_dir):
                        if base_name.lower() in df.lower():
                            doc_found = True
                            break
                # Check in README
                if not doc_found and base_name.lower() in readme_content.lower():
                    doc_found = True
                
                if doc_found:
                    documented_files += 1
            
            metrics["documentation_coverage"] = round(documented_files / len(python_files), 2)

        # 2. Visual Score (Mermaid blocks)
        visual_score = 0
        all_md_content = ""
        # Check README
        readme_path = os.path.join(repo_path, "README.md")
        if os.path.exists(readme_path):
            with open(readme_path, 'r', encoding='utf-8') as f:
                all_md_content += f.read()
        
        # Check docs/
        docs_dir = os.path.join(repo_path, "docs")
        if os.path.exists(docs_dir):
            for root, _, files in os.walk(docs_dir):
                for f in files:
                    if f.endswith(".md"):
                        with open(os.path.join(root, f), 'r', encoding='utf-8') as md_f:
                            all_md_content += md_f.read()
        
        mermaid_blocks = all_md_content.count("```mermaid")
        if mermaid_blocks >= 3:
            visual_score = 1.0
        elif mermaid_blocks >= 1:
            visual_score = 0.5
        
        metrics["readme_visual_score"] = visual_score

        # 3. Compliance Transparency
        compliance_data = self._analyze_compliance_capabilities(repo_path)
        implemented_count = sum(1 for status in compliance_data.values() if "Implemented" in str(status))
        
        metrics["compliance_transparency"] = round(implemented_count / len(compliance_data) if compliance_data else 0, 2)

        return metrics

    def _analyze_compliance_capabilities(self, repo_path):
        """Scans the codebase for compliance and auditing features and appends human observations."""
        print(f"[{self.name}] Scanning for compliance and auditing capabilities...")
        
        tools_dir = os.path.join(repo_path, "src", "tools")
        capabilities = {}
        
        check_map = {
            "audit_logging": ["fleet_logger.py", "security_audit_logger.py"],
            "rbac": ["rbac_manager.py"],
            "input_security": ["input_sanitizer.py", "safety_gate.py"],
            "network_security": ["egress_filter.py"],
            "traceability": ["snapshot_tester.py"]
        }
        
        for cap, files in check_map.items():
            found = []
            for f in files:
                if os.path.exists(os.path.join(tools_dir, f)):
                    found.append(f)
            
            if found:
                capabilities[cap] = f"Implemented via {', '.join(found)}"
            else:
                capabilities[cap] = "Not detected / Missing implementation"

        # Append human observations if they exist
        obs_path = os.path.join(repo_path, ".exegol", "human_observations.json")
        if os.path.exists(obs_path):
            try:
                with open(obs_path, 'r', encoding='utf-8') as f:
                    human_obs = json.load(f)
                if "compliance" in human_obs:
                    capabilities["human_observations"] = human_obs["compliance"]
                    print(f"[{self.name}] Appended human observations to compliance data.")
            except Exception as e:
                print(f"[{self.name}] Error reading human observations: {e}")

        return capabilities

