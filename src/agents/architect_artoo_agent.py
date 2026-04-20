import os
import json
import datetime
from tools.git_tool import has_commits_since


class ArchitectArtooAgent:
    """Reviews architecture, designs and governs app schemas, and ensures structural health.
    
    Responsible for maintaining the app.exegol.json standard and validating that all 
    scaffolded applications adhere to the core architecture principles.
    """

    def __init__(self, llm_client):
        self.llm_client = llm_client
        self.name = "ArchitectArtooAgent"
        self.max_steps = 10
        self.tools = ["diagram_generator", "readme_parser", "architecture_reviewer", "schema_designer"]
        self.success_metrics = {
            "schema_adherence_rate": {
                "description": "Percentage of apps passing the app.exegol.json validation check",
                "target": "100%",
                "current": None
            },
            "repos_with_arch_diagram": {
                "description": "Percentage of repos with an up-to-date Mermaid architecture diagram",
                "target": "100%",
                "current": None
            }
        }
        self.system_prompt = self.llm_client.generate_system_prompt(self)


    def execute(self, handoff):
        """Execute with a clean HandoffContext — no prior session memory required.

        Reads README and backlog from filesystem. Writes backlog tasks back.
        """
        repo_path = handoff.repo_path
        print(f"[{self.name}] Session {handoff.session_id} — waking up for repo: {repo_path}")

        # 1. Check if there were any commits in the past week
        has_new_commits = has_commits_since(repo_path, timeframe="1 week ago")

        if not has_new_commits:
            print(f"[{self.name}] No new commits in the last week. Going back to sleep.")
            return "No architecture updates needed (no commits)."

        print(f"[{self.name}] New commits detected. Analyzing architecture and README diagrams...")

        # 3. Check README for architecture diagram
        readme_path = os.path.join(repo_path, "README.md")
        has_diagram = False
        if os.path.exists(readme_path):
            try:
                with open(readme_path, 'r', encoding='utf-8') as f:
                    content = f.read()
                    if "```mermaid" in content or "Architecture Diagram" in content:
                        has_diagram = True
            except Exception as e:
                print(f"[{self.name}] Error reading README: {e}")

        exegol_dir = os.path.join(repo_path, ".exegol")
        os.makedirs(exegol_dir, exist_ok=True)
        backlog_file = os.path.join(exegol_dir, "backlog.json")
        reports_file = os.path.join(exegol_dir, "test_reports.json")

        backlog = []
        if os.path.exists(backlog_file):
            try:
                with open(backlog_file, 'r', encoding='utf-8') as f:
                    backlog = json.load(f)
            except Exception as e:
                print(f"[{self.name}] Error reading backlog: {e}")

        # 4. Integrate QualityQuigon reports into backlog
        if os.path.exists(reports_file):
            try:
                with open(reports_file, 'r', encoding='utf-8') as f:
                    reports = json.load(f)
                
                for report in reports:
                    if report.get("final_status") == "failed":
                        sandbox = report.get("sandbox")
                        tasks = report.get("validation", {})
                        failed_items = [k for k, v in tasks.items() if v.get("status") == "fail"]
                        
                        fix_task = {
                            "id": f"qa_{datetime.datetime.now().strftime('%M%S')}",
                            "summary": f"Fix QA failures in sandbox {sandbox}: {', '.join(failed_items)}",
                            "priority": "high",
                            "type": "bug_fix",
                            "status": "pending_prioritization",
                            "source_agent": "QualityQuigon"
                        }
                        # Avoid duplicates
                        if not any(f["summary"] == fix_task["summary"] for f in backlog):
                            backlog.append(fix_task)
            except Exception as e:
                print(f"[{self.name}] Error processing test reports: {e}")

        # 5. If no diagram, add a backlog task for ProductPoeAgent
        if not has_diagram:
            print(f"[{self.name}] No Mermaid diagram found in README. Backlogging diagram creation.")
            diagram_task = {
                "id": f"a_{len(backlog)+1:03d}",
                "summary": "Update README.md with an accurate Mermaid architecture diagram",
                "priority": "high",
                "type": "documentation",
                "status": "pending_prioritization"
            }
            if not any(f["summary"] == diagram_task["summary"] for f in backlog):
                backlog.append(diagram_task)

        # 6. Backlog broader solution architecture improvements
        print(f"[{self.name}] Evaluating broader solution architecture...")
        architecture_task = {
            "id": f"a_{len(backlog)+2:03d}",
            "summary": "Evaluate architecture for scaling bottlenecks introduced by recent commits",
            "priority": "medium",
            "type": "architecture_review",
            "status": "pending_prioritization"
        }
        if not any(f["summary"] == architecture_task["summary"] for f in backlog):
            backlog.append(architecture_task)

        # Save back to backlog
        with open(backlog_file, 'w', encoding='utf-8') as f:
            json.dump(backlog, f, indent=4)

        return f"Architecture review complete. Documentation checked and backlog updated in {backlog_file}."
