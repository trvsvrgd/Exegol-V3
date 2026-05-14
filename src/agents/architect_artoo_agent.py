import os
import json
import datetime
from tools.git_tool import has_commits_since, get_recent_commits
from tools.web_search import web_search
from tools.backlog_manager import BacklogManager
from tools.readme_parser import ReadmeParser
from tools.diagram_generator import DiagramGenerator
from tools.architecture_reviewer import ArchitectureReviewer
from tools.schema_designer import SchemaDesigner
from tools.fleet_logger import log_interaction
from tools.sandbox_validator import validate_app_schema


class ArchitectArtooAgent:
    """Reviews architecture, designs and governs app schemas, and ensures structural health.
    
    Responsible for maintaining the app.exegol.json standard and validating that all 
    scaffolded applications adhere to the core architecture principles.
    """

    def __init__(self, llm_client):
        self.llm_client = llm_client
        self.name = "ArchitectArtooAgent"
        self.max_steps = 5  # Optimized: utilization was 8%, budget freed (optimize_architect_artoo)
        self.tools = ["diagram_generator", "readme_parser", "architecture_reviewer", "schema_designer", "web_search"]
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
        is_analysis_request = "analyze" in (handoff.scheduled_prompt or "").lower() or "ops_intel" in (handoff.scheduled_prompt or "").lower()

        if not has_new_commits and not is_analysis_request:
            print(f"[{self.name}] No new commits and no analysis request. Going back to sleep.")
            return "No architecture updates needed (no commits)."

        if is_analysis_request:
            print(f"[{self.name}] Analysis request detected. Reviewing operational logs...")
        elif has_new_commits:
            recent_commits = get_recent_commits(repo_path, timeframe="1 week ago")
            print(f"[{self.name}] {len(recent_commits)} new commit(s) detected. Analyzing architecture...")

        bm = BacklogManager(repo_path)
        tasks_added = []

        # 2. Archive completed tasks to keep the active backlog clean
        archived = bm.archive_completed_tasks()
        if archived > 0:
            print(f"[{self.name}] Archived {archived} completed task(s) from backlog.")

        # 3. Check README for Mermaid architecture diagram
        readme_data = ReadmeParser.parse(repo_path)
        has_diagram = readme_data.get("has_mermaid", False)

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
        print(f"[{self.name}] Researching latest design patterns for this stack...")
        arch_query = "latest micro-agent architecture patterns and filesystem-as-state best practices 2024 2025"
        arch_research = web_search(arch_query, num_results=3)
        
        print(f"[{self.name}] Performing deep architecture review...")
        try:
            review_report = ArchitectureReviewer.review(repo_path, client=self.llm_client)
        except Exception as rev_err:
            print(f"[{self.name}] Architecture review failed (non-fatal): {rev_err}")
            review_report = {"status": "STABLE", "findings": [], "error": str(rev_err)}
        
        arch_tasks = []
        if review_report.get("status") in ["DEGRADED", "CRITICAL"]:
            for finding in review_report.get("findings", []):
                arch_tasks.append({
                    "id": f"arch_fix_{finding[:12].lower().replace(' ', '_')}",
                    "summary": f"Architectural Issue: {finding}",
                    "priority": "high",
                    "type": "architecture_improvement",
                    "status": "pending_prioritization",
                    "source_agent": self.name,
                    "rationale": "Automated architectural review identified this concern.",
                    "created_at": datetime.datetime.now().isoformat()
                })

        # Add predefined tasks if they are not already there
        standard_tasks = [
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

        arch_tasks.extend(standard_tasks)

        for task in arch_tasks:
            added = bm.add_task(task)
            if added:
                tasks_added.append(task["id"])
                print(f"[{self.name}] Backlogged: {task['id']}")

        # 6. Calculate Success Metrics for reporting
        all_apps = []
        sandboxes_dir = os.path.join(repo_path, ".exegol", "sandboxes")
        if os.path.exists(sandboxes_dir):
            for entry in os.scandir(sandboxes_dir):
                if entry.is_dir(follow_symlinks=True):
                    if "app.exegol.json" in os.listdir(entry.path):
                        all_apps.append(entry.path)
        
        passed_schema = 0
        schema_path = os.path.join(repo_path, ".exegol", "schemas", "app_schema.json")
        for app_path in all_apps:
            val = validate_app_schema(app_path, schema_path)
            if val.get("status") == "pass":
                passed_schema += 1
        
        schema_rate = (passed_schema / len(all_apps) * 100) if all_apps else 100.0
        self.success_metrics["schema_adherence_rate"]["current"] = f"{schema_rate:.1f}%"
        self.success_metrics["repos_with_arch_diagram"]["current"] = "100%" if has_diagram else "0%"

        # Log metrics to fleet reports
        reports_dir = os.path.join(exegol_dir, "fleet_reports")
        os.makedirs(reports_dir, exist_ok=True)
        metrics_path = os.path.join(reports_dir, f"metrics_{self.name.lower()}.json")
        with open(metrics_path, 'w', encoding='utf-8') as f:
            json.dump({
                "timestamp": datetime.datetime.now().isoformat(),
                "metrics": self.success_metrics,
                "apps_scanned": len(all_apps)
            }, f, indent=4)

        summary = (
            f"Architecture review complete. "
            f"{archived} task(s) archived. "
            f"{len(tasks_added)} new task(s) added. "
            f"Metrics: Schema Adherence {self.success_metrics['schema_adherence_rate']['current']}, "
            f"Diagram Presence {self.success_metrics['repos_with_arch_diagram']['current']}."
        )
        print(f"[{self.name}] {summary}")

        log_interaction(
            agent_id=self.name,
            outcome="success",
            task_summary=summary,
            repo_path=repo_path,
            session_id=handoff.session_id,
            metrics={
                "schema_adherence": self.success_metrics['schema_adherence_rate']['current'],
                "diagram_presence": self.success_metrics['repos_with_arch_diagram']['current']
            }
        )

        # 7. Determination: Should we trigger Anakin for risk assessment?
        if len(arch_tasks) > 5 or schema_rate < 90.0:
            print(f"[{self.name}] DETERMINATION: High architectural debt or schema drift. Triggering AssessmentAnakin...")
            self.next_agent_id = "assessment_anakin"
        else:
            self.next_agent_id = None

        return summary
