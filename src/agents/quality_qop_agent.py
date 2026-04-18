import os
import json


class QualityQopAgent:
    """Handles QA testing, determines appropriate testing levels (UAT, unit, linting), and provides feedback."""

    def __init__(self, llm_client):
        self.llm_client = llm_client
        self.name = "QualityQopAgent"
        self.max_steps = 15
        self.tools = ["test_runner", "linter", "uat_sandbox"]
        self.success_metrics = {
            "defect_escape_rate": {
                "description": "Percentage of bugs that reach production undetected",
                "target": "0%",
                "current": None
            },
            "test_coverage_pct": {
                "description": "Code coverage percentage for target repo",
                "target": ">=80%",
                "current": None
            },
            "false_positive_rate": {
                "description": "Percentage of test failures that are flaky or false positives",
                "target": "<=2%",
                "current": None
            }
        }
        self.system_prompt = self.llm_client.generate_system_prompt(self)

    def execute(self, handoff):
        """Execute with a clean HandoffContext — no prior session memory required.

        Reads test state from filesystem, runs tests, writes results back.
        """
        repo_path = handoff.repo_path
        print(f"[{self.name}] Session {handoff.session_id} — waking up for repo: {repo_path}")
        print(f"[{self.name}] Determining appropriate level of testing (UAT, unit tests, linting)...")

        exegol_dir = os.path.join(repo_path, ".exegol")
        os.makedirs(exegol_dir, exist_ok=True)
        reports_file = os.path.join(exegol_dir, "test_reports.json")

        reports = []
        if os.path.exists(reports_file):
            try:
                with open(reports_file, 'r', encoding='utf-8') as f:
                    reports = json.load(f)
            except Exception as e:
                print(f"[{self.name}] Error reading test reports: {e}")

        # Mock testing logic
        new_report = {
            "id": f"rep_{len(reports)+1:03d}",
            "type": "unit_tests",
            "status": "passed",
            "issues": []
        }
        reports.append(new_report)

        with open(reports_file, 'w', encoding='utf-8') as f:
            json.dump(reports, f, indent=4)

        return f"QA testing completed. Results saved to {reports_file}."
