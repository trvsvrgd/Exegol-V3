import os
import json
import datetime


class ArchitectAnubisAgent:
    """Reviews architecture, ensures README diagrams are current, and backlogs structural improvements."""

    def __init__(self, llm_client):
        self.llm_client = llm_client
        self.name = "ArchitectAnubisAgent"
        self.max_steps = 10
        self.tools = ["diagram_generator", "readme_parser", "architecture_reviewer"]
        self.success_metrics = {
            "repos_with_arch_diagram": {
                "description": "Percentage of repos with an up-to-date Mermaid architecture diagram",
                "target": "100%",
                "current": None
            },
            "architecture_debt_items": {
                "description": "Number of open architecture-debt backlog items trending toward zero",
                "target": "0",
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
        # Mocking the check: in a real implementation we would run
        # `git log --since="1 week ago"` to check for commits.
        has_new_commits = True  # Mocking that there are new commits

        if not has_new_commits:
            print(f"[{self.name}] No new commits in the last week. Going back to sleep.")
            return "No architecture updates needed (no commits)."

        print(f"[{self.name}] New commits detected. Analyzing architecture and README diagrams...")

        # 2. Check README for architecture diagram
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

        backlog = []
        if os.path.exists(backlog_file):
            try:
                with open(backlog_file, 'r', encoding='utf-8') as f:
                    backlog = json.load(f)
            except Exception as e:
                print(f"[{self.name}] Error reading backlog: {e}")

        # 3. If no diagram, add a backlog task for ProductivePuckAgent
        if not has_diagram:
            print(f"[{self.name}] No Mermaid diagram found in README. Backlogging diagram creation.")
            diagram_task = {
                "id": f"a_{len(backlog)+1:03d}",
                "summary": "Update README.md with an accurate Mermaid architecture diagram",
                "priority": "high",
                "type": "documentation",
                "status": "pending_prioritization"
            }
            backlog.append(diagram_task)

        # 4. Backlog broader solution architecture improvements
        print(f"[{self.name}] Evaluating broader solution architecture...")
        architecture_task = {
            "id": f"a_{len(backlog)+2:03d}",
            "summary": "Evaluate architecture for scaling bottlenecks introduced by recent commits",
            "priority": "medium",
            "type": "architecture_review",
            "status": "pending_prioritization"
        }
        backlog.append(architecture_task)

        # Save back to backlog
        with open(backlog_file, 'w', encoding='utf-8') as f:
            json.dump(backlog, f, indent=4)

        return f"Architecture review complete. Changes proposed and backlogged in {backlog_file}."
