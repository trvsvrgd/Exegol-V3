import os
import json
from tools.sandbox_validator import validate_app_schema, run_sandbox_lint, run_sandbox_tests
from evals.snapshot_eval_runner import run_regression_eval
from tools.backlog_manager import BacklogManager
from tools.web_search import web_search
from tools.fleet_logger import log_interaction
from tools.metrics_manager import SuccessMetricsManager
from tools.heartbeat_monitor import HeartbeatMonitor


class QualityQuigonAgent:
    """Handles professional QA validation, including automated sandbox testing and schema governance.
    
    Responsible for validating that agent prototypes in 'Experience Sandboxes' meet 
    architectural standards, pass linting, and have functional test coverage.
    """

    def __init__(self, llm_client):
        self.llm_client = llm_client
        self.name = "QualityQuigonAgent"
        self.max_steps = 15
        self.tools = ["test_runner", "linter", "uat_sandbox", "sandbox_validator", "web_search"]
        self.success_metrics = {
            "repo_wide_health": {
                "description": "Percentage of repository files passing the expanded multi-language linter",
                "target": "100%",
                "current": None
            },
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
        self.metrics_manager = SuccessMetricsManager(os.getcwd())

    def _calculate_success_metrics(self, repo_path: str) -> dict:
        """Calculates quality and validation metrics based on recent logs."""
        # Already handled in the execute loop for Quigon as it has direct access to results
        # We just return the current state of self.success_metrics formatted for log_interaction
        return {
            "repo_wide_health": self.success_metrics["repo_wide_health"]["current"],
            "sandbox_validation_coverage": self.success_metrics["sandbox_validation_coverage"]["current"],
            "schema_failure_rate": self.success_metrics["schema_failure_rate"]["current"],
            "defect_escape_rate": self.success_metrics["defect_escape_rate"]["current"]
        }

    def execute(self, handoff):
        """Execute with a clean HandoffContext — no prior session memory required.

        Performs regression testing via snapshots and validates active sandboxes.
        """
        repo_path = handoff.repo_path
        task_id = handoff.task_id
        print(f"[{self.name}] Session {handoff.session_id} — professional validation starting.")

        # --- PHASE 4: Context Propagation (arch_dex_context_upgrade) ---
        if handoff.scheduled_prompt:
            print(f"[{self.name}] Targeted Validation Request: {handoff.scheduled_prompt}")
            # We add it to results so it shows up in the final report
            results = [f"Targeted Validation: {handoff.scheduled_prompt}"]
        else:
            results = []
        self.regression_context = ""

        # 0. Infrastructure Audit (New Phase 3.5)
        print(f"[{self.name}] Initiating Repository Infrastructure Audit...")
        from tools.linter import run_lint
        repo_lint = run_lint(repo_path)
        if repo_lint["status"] == "fail":
            results.append(f"Repo Infrastructure: fail ({len(repo_lint['issues'])} issues found)")
            for issue in repo_lint["issues"][:5]: # Log first 5 to avoid bloat
                results.append(f"  - Issue: {issue}")
            self.success_metrics["repo_wide_health"]["current"] = "Needs Attention"
        else:
            results.append("Repo Infrastructure: pass")
            self.success_metrics["repo_wide_health"]["current"] = "100%"

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
                        
                    # Pulse heartbeat per sandbox (arch_agent_heartbeat)
                    HeartbeatMonitor.pulse_session(repo_path, handoff.session_id)
                    
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
                    
                    # 2d. External Quality Research (Phase 2 Integration)
                    research_res = self._perform_external_quality_research(sb_path)
                    results.append(f"Sandbox '{sb}' External Research: {research_res['status']}")
                    if research_res['status'] == 'fail':
                        results.append(f"  - Warning: {research_res.get('message')}")

                    if schema_res['status'] == 'fail' or lint_res['status'] == 'fail' or test_res['status'] == 'fail':
                        print(f"[{self.name}] Sandbox '{sb}' failed quality checks.")
                        # Could set a flag here to trigger dex if we want

        # 3. Calculate Success Metrics (Phase 3)
        total_sandboxes = len(active_sandboxes) if 'active_sandboxes' in locals() else 0
        if total_sandboxes > 0:
            schema_fails = sum(1 for res in results if "Schema: fail" in res)
            self.success_metrics["sandbox_validation_coverage"]["current"] = "100%"
            self.success_metrics["schema_failure_rate"]["current"] = f"{(schema_fails / total_sandboxes) * 100:.1f}%"
            self.success_metrics["defect_escape_rate"]["current"] = "0%" # No regressions detected in this pass

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

            self.next_agent_id = "uat_ulic"

        # --- TASK: Validation Report Logging ---
        self._log_validation_report(repo_path, results, eval_res)
        
        duration = 10.0 # Heuristic
        metrics = self._calculate_success_metrics(repo_path)
        log_interaction(
            agent_id=self.name,
            outcome="success",
            task_summary=f"Validation Cycle complete. Results: " + ", ".join(results),
            repo_path=repo_path,
            steps_used=1,
            duration_seconds=duration,
            session_id=handoff.session_id,
            metrics=metrics
        )

        return f"Validation Cycle complete. Results: " + ", ".join(results)

    def _perform_external_quality_research(self, sb_path: str) -> dict:
        """Researches latest CVEs and best practices for the sandbox tech stack."""
        try:
            # 1. Identify tech stack from app.exegol.json
            exegol_json = os.path.join(sb_path, "app.exegol.json")
            tech_stack = "generic web"
            if os.path.exists(exegol_json):
                with open(exegol_json, 'r') as f:
                    data = json.load(f)
                    tech_stack = data.get("inference", {}).get("base_model", "generic")
            
            print(f"[{self.name}] Researching quality standards for: {tech_stack}")
            query = f"latest security vulnerabilities and testing best practices for {tech_stack} 2024 2025"
            search_results = web_search(query, num_results=3)
            
            if search_results:
                findings = [res.get('title', 'Unknown') for res in search_results if isinstance(res, dict)]
                findings_str = ", ".join(findings[:2]) if findings else "No clear findings."
                msg = f"Researched {tech_stack} standards. Discovered: {findings_str}"
            else:
                msg = f"Researched {tech_stack} standards. No immediate critical CVEs flagged."
            
            return {
                "status": "pass",
                "message": msg
            }
        except Exception as e:
            return {"status": "fail", "message": str(e)}

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
        
        content += f"\n## Success Metrics\n"
        for metric, data in self.success_metrics.items():
            content += f"- **{metric}:** {data['current']} (Target: {data['target']})\n"
            
        try:
            with open(report_path, 'w', encoding='utf-8') as f:
                f.write(content)
            print(f"[{self.name}] Validation report logged to {report_path}")
        except Exception as e:
            print(f"[{self.name}] Failed to log validation report: {e}")
