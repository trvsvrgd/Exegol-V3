import os
import json
import datetime
from tools.git_tool import has_commits_since, get_recent_commits
from tools.backlog_manager import BacklogManager


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

        Reads README, QA reports, and backlog from filesystem. Archives completed
        tasks, checks structural health, and writes architecture improvement tasks
        back to the backlog for ProductPoe to prioritize.
        """
        repo_path = handoff.repo_path
        exegol_dir = os.path.join(repo_path, ".exegol")
        print(f"[{self.name}] Session {handoff.session_id} — waking up for repo: {repo_path}")

        # 1. Check if there were any commits in the past week
        has_new_commits = has_commits_since(repo_path, timeframe="1 week ago")
        if not has_new_commits:
            print(f"[{self.name}] No new commits in the last week. Going back to sleep.")
            return "No architecture updates needed (no commits)."

        recent_commits = get_recent_commits(repo_path, timeframe="1 week ago")
        print(f"[{self.name}] {len(recent_commits)} new commit(s) detected. Analyzing architecture...")

        bm = BacklogManager(repo_path)
        tasks_added = []

        # 2. Archive completed tasks to keep the active backlog clean
        archived = bm.archive_completed_tasks()
        if archived > 0:
            print(f"[{self.name}] Archived {archived} completed task(s) from backlog.")

        # 3. Check README for Mermaid architecture diagram
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

        if not has_diagram:
            print(f"[{self.name}] No Mermaid diagram found in README. Backlogging diagram update.")
            added = bm.add_task({
                "id": "arch_readme_diagram",
                "summary": "Update README.md with an accurate Mermaid architecture diagram",
                "priority": "high",
                "type": "documentation",
                "status": "pending_prioritization",
                "source_agent": self.name,
                "created_at": datetime.datetime.now().isoformat()
            })
            if added:
                tasks_added.append("arch_readme_diagram")

        # 4. Integrate QualityQuigon test reports into backlog
        reports_file = os.path.join(exegol_dir, "test_reports.json")
        if os.path.exists(reports_file):
            try:
                with open(reports_file, 'r', encoding='utf-8') as f:
                    reports_data = json.load(f)

                reports = reports_data if isinstance(reports_data, list) else [reports_data]

                for report in reports:
                    status = report.get("final_status") or report.get("regression_status")
                    if status in ["failed", "fail"]:
                        sandbox = report.get("sandbox", report.get("task_id", "unknown"))
                        tasks = report.get("validation", {})
                        failed_items = [k for k, v in tasks.items() if isinstance(v, dict) and v.get("status") == "fail"]
                        task_id = f"qa_fix_{str(sandbox)[:12]}"
                        summary = f"Fix QA failures in sandbox {sandbox}"
                        if failed_items:
                            summary += f": {', '.join(failed_items)}"
                        added = bm.add_task({
                            "id": task_id,
                            "summary": summary,
                            "priority": "high",
                            "type": "bug_fix",
                            "status": "pending_prioritization",
                            "source_agent": self.name,
                            "created_at": datetime.datetime.now().isoformat()
                        })
                        if added:
                            tasks_added.append(task_id)
            except Exception as e:
                print(f"[{self.name}] Error processing test reports: {e}")

        # 5. Evaluate broader solution architecture gaps and inject tasks
        print(f"[{self.name}] Evaluating broader solution architecture gaps...")
        arch_tasks = [
            {
                "id": "arch_tool_registry",
                "summary": "Implement missing Artoo tools: diagram_generator, readme_parser, architecture_reviewer, schema_designer",
                "priority": "high",
                "type": "architecture_gap",
                "status": "pending_prioritization",
                "source_agent": self.name,
                "rationale": "ArchitectArtoo declares these tools in its manifest but none are implemented. The agent cannot hit its schema_adherence_rate and repos_with_arch_diagram KPIs without them.",
                "created_at": datetime.datetime.now().isoformat()
            },
            {
                "id": "arch_app_schema_validator",
                "summary": "Implement app.exegol.json schema validator and enforce it in the DeveloperDex sandbox lifecycle",
                "priority": "high",
                "type": "architecture_governance",
                "status": "pending_prioritization",
                "source_agent": self.name,
                "rationale": ".exegol/schemas/app_schema.json exists but no agent validates sandbox apps against it. Schema adherence is an Artoo KPI with a 100% target that is currently unmeasured.",
                "created_at": datetime.datetime.now().isoformat()
            },
            {
                "id": "arch_handoff_loop_guard",
                "summary": "Add circuit-breaker and loop-depth guard to orchestrator autonomous agent chaining",
                "priority": "high",
                "type": "architecture_resilience",
                "status": "pending_prioritization",
                "source_agent": self.name,
                "rationale": "orchestrator.wake_and_execute_agent() recurses via next_agent_id with no max-depth or loop-detection guard. A Dex->Quigon->Dex regression cycle can spin indefinitely and exhaust API quota.",
                "created_at": datetime.datetime.now().isoformat()
            },
            {
                "id": "arch_api_auth_layer",
                "summary": "Add API key authentication middleware to all FastAPI endpoints in api.py (CORS is currently wildcard *)",
                "priority": "high",
                "type": "security_architecture",
                "status": "pending_prioritization",
                "source_agent": self.name,
                "rationale": "api.py has allow_origins=['*'] with zero authentication. Any local process can trigger agent execution or mutate the backlog via /run-task, /backlog/update, /human-queue/action, etc.",
                "created_at": datetime.datetime.now().isoformat()
            },
            {
                "id": "arch_hitl_queue_migration",
                "summary": "Migrate VibeVader output from user_action_required.md to user_action_required.json for Control Tower HITL loop",
                "priority": "high",
                "type": "architecture_migration",
                "status": "pending_prioritization",
                "source_agent": self.name,
                "rationale": "The /human-queue API endpoint reads user_action_required.json but VibeVader writes to a .md file. This breaks the Control Tower HITL loop entirely — the UI queue will always be empty.",
                "created_at": datetime.datetime.now().isoformat()
            },
            {
                "id": "arch_handoff_hmac",
                "summary": "Add HMAC signature to HandoffContext and validate in SessionManager before spawning any agent session",
                "priority": "medium",
                "type": "security_architecture",
                "status": "pending_prioritization",
                "source_agent": self.name,
                "rationale": "HandoffContext is an unsigned frozen dataclass. A forged or corrupted handoff can redirect agent execution scope without detection. Addresses SEC-ARCH-005 recommendation.",
                "created_at": datetime.datetime.now().isoformat()
            },
        ]

        for task in arch_tasks:
            added = bm.add_task(task)
            if added:
                tasks_added.append(task["id"])
                print(f"[{self.name}] Backlogged: {task['id']}")

        summary = (
            f"Architecture review complete. "
            f"{archived} task(s) archived. "
            f"{len(tasks_added)} new task(s) added: "
            f"{', '.join(tasks_added) if tasks_added else 'none (all already present)'}."
        )
        print(f"[{self.name}] {summary}")
        return summary
