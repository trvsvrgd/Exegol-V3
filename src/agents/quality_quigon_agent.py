import os
import json
from tools.sandbox_validator import validate_app_schema, run_sandbox_lint, run_sandbox_tests
from evals.snapshot_eval_runner import run_regression_eval
from tools.backlog_manager import BacklogManager


class QualityQuigonAgent:
    """Handles professional QA validation, including automated sandbox testing and schema governance.
    
    Responsible for validating that agent prototypes in 'Experience Sandboxes' meet 
    architectural standards, pass linting, and have functional test coverage.
    """

    def __init__(self, llm_client):
        self.llm_client = llm_client
        self.name = "QualityQuigonAgent"
        self.max_steps = 15
        self.tools = ["test_runner", "linter", "uat_sandbox", "sandbox_validator"]
        self.success_metrics = {
            "sandbox_validation_coverage": {
                "description": "Percentage of active sandboxes that have been automatically validated",
                "target": "100%",
                "current": None
            },
            "schema_failure_rate": {
                "description": "Percentage of sandboxes failing app.exegol.json validation",
                "target": "<=5%",
                "current": None
            },
            "defect_escape_rate": {
                "description": "Percentage of bugs that reach production undetected",
                "target": "0%",
                "current": None
            }
        }
        self.system_prompt = self.llm_client.generate_system_prompt(self)

    def execute(self, handoff):
        """Execute with a clean HandoffContext — no prior session memory required.

        Performs regression testing via snapshots and validates active sandboxes.
        """
        repo_path = handoff.repo_path
        task_id = handoff.task_id
        print(f"[{self.name}] Session {handoff.session_id} — professional validation starting.")

        results = []
        self.regression_context = ""

        # 1. Snapshot Regression Check (poe_009)
        print(f"[{self.name}] Checking for snapshots/baseline for task: {task_id}")
        
        # Use actual sandbox state if available for regression, otherwise use the handoff hash
        exegol_dir = os.path.join(repo_path, ".exegol")
        sandboxes_dir = os.path.join(exegol_dir, "sandboxes")
        
        # Capture a 'current' snapshot of active sandboxes for comparison
        current_state = {"sandboxes": []}
        if os.path.isdir(sandboxes_dir):
            current_state["sandboxes"] = sorted(os.listdir(sandboxes_dir))

        eval_res = run_regression_eval(current_state, f"qa_baseline_{task_id}")
        results.append(f"State Regression: {eval_res.get('status', 'unknown')}")

        if eval_res.get("status") == "fail":
            self.regression_context = f"Fleet state mismatch detected. Target: {task_id}. Baseline differs from current sandbox allocation."

        # 2. Sandbox Validation (Existing logic)
        exegol_dir = os.path.join(repo_path, ".exegol")
        sandboxes_dir = os.path.join(exegol_dir, "sandboxes")
        reports_file = os.path.join(exegol_dir, "test_reports.json")

        if os.path.isdir(sandboxes_dir):
            active_sandboxes = [d for d in os.listdir(sandboxes_dir) if os.path.isdir(os.path.join(sandboxes_dir, d))]
            if active_sandboxes:
                print(f"[{self.name}] Found {len(active_sandboxes)} active sandboxes. Validating...")
                schema_path = os.path.join(repo_path, ".exegol", "schemas", "app_schema.json")
                
                for sb in active_sandboxes:
                    sb_path = os.path.join(sandboxes_dir, sb)
                    
                    # 2a. Schema Check
                    if not os.path.exists(schema_path):
                        results.append(f"Sandbox '{sb}' Schema: error (Master schema missing)")
                        continue
                        
                    schema_res = validate_app_schema(sb_path, schema_path)
                    results.append(f"Sandbox '{sb}' Schema: {schema_res['status']}")
                    if schema_res['status'] == 'fail':
                        results.append(f"  - Failure: {schema_res.get('message')}")
                    
                    # 2b. Linting
                    lint_res = run_sandbox_lint(sb_path)
                    results.append(f"Sandbox '{sb}' Lint: {lint_res['status']}")
                    
                    # 2c. Automated Tests
                    test_res = run_sandbox_tests(sb_path)
                    results.append(f"Sandbox '{sb}' Tests: {test_res['status']}")
                    
                    if schema_res['status'] == 'fail' or lint_res['status'] == 'fail' or test_res['status'] == 'fail':
                        print(f"[{self.name}] Sandbox '{sb}' failed quality checks.")
                        # Could set a flag here to trigger dex if we want

        # Final Report
        report_data = {
            "session_id": handoff.session_id,
            "task_id": task_id,
            "regression_status": eval_res.get("status"),
            "timestamp": handoff.timestamp
        }
        with open(reports_file, 'w', encoding='utf-8') as f:
            json.dump(report_data, f, indent=4)

        if eval_res.get("status") == "fail":
            print(f"[{self.name}] Regression detected! Auto-triggering DeveloperDex for correction.")
            self.next_agent_id = "developer_dex"
        else:
            # Task Closure & Archival
            if task_id and task_id != "fleet_cycle":
                bm = BacklogManager(repo_path)
                print(f"[{self.name}] Task {task_id} passed validation. Marking as completed and archiving...")
                bm.update_task_status(task_id, "completed")
                archived_count = bm.archive_completed_tasks()
                results.append(f"Task {task_id} closed and archived.")

            self.next_agent_id = "architect_artoo"

        # --- TASK: Validation Report Logging ---
        self._log_validation_report(repo_path, results, eval_res)

        return f"Validation Cycle complete. Results: " + ", ".join(results)

    def _log_validation_report(self, repo_path: str, results: list, eval_res: dict):
        """Logs a human-readable validation report for the user."""
        logs_dir = os.path.join(repo_path, ".exegol", "interaction_logs")
        os.makedirs(logs_dir, exist_ok=True)
        
        import time
        timestamp = time.strftime("%Y%m%d_%H%M%S")
        report_path = os.path.join(logs_dir, f"report_quigon_{timestamp}.md")
        
        content = f"# Validation Report: QualityQuigon\n"
        content += f"**Timestamp:** {time.ctime()}\n\n"
        
        content += f"## Summary Results\n"
        for res in results:
            content += f"- {res}\n"
        
        content += f"\n## Regression Details\n"
        content += f"- **Status:** {eval_res.get('status', 'unknown')}\n"
        if self.regression_context:
            content += f"- **Context:** {self.regression_context}\n"
            
        try:
            with open(report_path, 'w', encoding='utf-8') as f:
                f.write(content)
            print(f"[{self.name}] Validation report logged to {report_path}")
        except Exception as e:
            print(f"[{self.name}] Failed to log validation report: {e}")
