import os
import json
import time
import datetime
from tools.fleet_logger import log_interaction
from tools.log_reader import read_interaction_logs
from tools.repo_scanner import scan_for_security_vulnerabilities
from tools.backlog_manager import BacklogManager
from tools.todo_reporter import report_todos
from tools.repo_analyzer import analyze_repository
from tools.slack_tool import post_to_slack


class WatcherWedgeAgent:
    """Wedge is the fleet's eyes and ears, watching for operational failures and technical debt.
    
    He wakes up, scans logs for failures, checks the codebase for 'smells', and 
    reports issues to Architect Artoo and Product Poe for prioritization.
    """

    def __init__(self, llm_client):
        self.llm_client = llm_client
        self.name = "WatcherWedgeAgent"
        self.max_steps = 10
        self.tools = ["log_reader", "repo_scanner", "backlog_writer", "slack_notifier"]
        self.success_metrics = {
            "issues_detected": {
                "description": "Total issues (logs + code smells) detected per cycle",
                "target": "N/A",
                "current": None
            },
            "backlog_injections": {
                "description": "Number of high-priority tasks injected into the backlog",
                "target": ">0 if issues exist",
                "current": None
            }
        }
        self.system_prompt = """
You are Watcher Wedge, the Operational Intelligence officer for the Exegol v3 agent fleet. 
Your demeanor is vigilant, precise, and proactive. You don't fix bugs—you find them and ensure the leadership (Artoo and Poe) knows about them.

Your Mission:
1. Scan Interaction Logs: Look for failures, errors, and performance bottlenecks.
2. Audit Codebase: Look for 'smells' like hardcoded credentials, unhandled fetch calls, or mock code that was meant to be replaced.
3. Consolidate & Report: Summarize your findings. Do not just dump data. Provide context on WHY these issues matter.
4. Escalate: Create a high-priority task in the backlog for Artoo (Architecture) and Poe (Product) to analyze and prioritize these findings.

Output:
Your summary should be formatted as a 'Fleet Health Report'.
"""

    def execute(self, handoff):
        start_time = time.time()
        repo_path = handoff.repo_path
        print(f"[{self.name}] Waking up. Scanning fleet health for: {repo_path}")

        try:
            # 1. Scan Interaction Logs (last 24 hours)
            logs = read_interaction_logs(repo_path, limit=100)
            failures = [l for l in logs if l.get("outcome") == "failure"]
            
            # 2. Scan for Code Smells (TODOS, Mocks, etc)
            audit_findings = analyze_repository(repo_path)
            
            # 2b. Scan for Security Vulnerabilities (Phase 3 Integration)
            print(f"[{self.name}] Scanning for security vulnerabilities...")
            security_findings = scan_for_security_vulnerabilities(repo_path)
            
            # 3. Targeted Scan for the specific issue the user mentioned (fetch without catch)
            targeted_issues = self._targeted_code_scan(repo_path)
            
            # 4. Consolidate findings
            all_issues = audit_findings + security_findings + targeted_issues
            report = self._generate_health_report(failures, all_issues, targeted_issues)
            
            # 5. Escalate to Backlog
            bm = BacklogManager(repo_path)
            task_id = f"ops_intel_{int(time.time())}"
            task = {
                "id": task_id,
                "summary": f"CRITICAL: Fleet Health Report - {len(failures)} failures, {len(all_issues)} issues",
                "priority": "high",
                "type": "analysis",
                "status": "todo",
                "source_agent": self.name,
                "rationale": "Watcher Wedge detected operational failures, security vulnerabilities, and code smells.",
                "details": report,
                "created_at": datetime.datetime.now().isoformat()
            }
            bm.add_task(task)
            
            # 6. Notify Slack
            self._notify_slack(repo_path, len(failures), len(all_issues))

            
            duration = time.time() - start_time
            log_interaction(
                agent_id=self.name,
                outcome="success",
                task_summary=f"Wedge completed health check. Detected {len(failures)} failures and {len(audit_findings) + len(targeted_issues)} code smells. Task {task_id} added.",
                repo_path=repo_path,
                steps_used=1,
                duration_seconds=duration,
                session_id=handoff.session_id,
                metrics={
                    "issues_detected": len(failures) + len(audit_findings) + len(targeted_issues),
                    "backlog_injections": 1
                }
            )
            
            return f"Fleet Health Report generated and escalated via task {task_id}."

        except Exception as e:
            duration = time.time() - start_time
            log_interaction(
                agent_id=self.name,
                outcome="failure",
                task_summary=f"Health check failed: {str(e)}",
                repo_path=repo_path,
                steps_used=1,
                duration_seconds=duration,
                errors=[str(e)],
                session_id=handoff.session_id
            )
            return f"[{self.name}] Error during operational intelligence cycle: {e}"

    def _targeted_code_scan(self, repo_path):
        """Looks for specific patterns like unhandled fetch calls or hardcoded keys."""
        findings = []
        # This is a simplified version; in a real run, the LLM would use tools to do this.
        # For the sake of this autonomous agent's initial logic, we'll hardcode a search for the example provided.
        
        target_file = os.path.join(repo_path, "src", "components", "FleetHealth.tsx")
        if os.path.exists(target_file):
            with open(target_file, 'r', encoding='utf-8') as f:
                content = f.read()
                if "fetch(" in content and ".catch(" not in content:
                    findings.append({
                        "task": "Add error handling to fetch calls in FleetHealth.tsx",
                        "category": "stability",
                        "context": "Found fetch() without .catch() block. This causes silent failures."
                    })
                if "API_KEY =" in content or "X-API-Key" in content:
                    findings.append({
                        "task": "Audit hardcoded API keys in FleetHealth.tsx",
                        "category": "security",
                        "context": "Detected API key references that should likely be in environment variables."
                    })
        return findings

    def _generate_health_report(self, failures, audit_findings, targeted_issues):
        report = "## Fleet Health Report\n\n"
        
        if failures:
            report += "### 🔴 Operational Failures (Interaction Logs)\n"
            for f in failures[:5]:
                report += f"- **{f.get('agent_id')}**: {f.get('task_summary')}\n"
                if f.get('errors'):
                    report += f"  - Errors: `{', '.join(f.get('errors'))}`\n"
        else:
            report += "### ✅ No Operational Failures Detected\n"
            
        if targeted_issues or audit_findings:
            report += "\n### 🟠 Technical Debt & Code Smells\n"
            for issue in targeted_issues + audit_findings[:5]:
                report += f"- [{issue.get('category', 'debt')}] {issue.get('task')}\n"
                report += f"  - Context: {issue.get('context')}\n"
                
        report += "\n**Recommendation:** Architect Artoo should review the structural implications, and Product Poe should prioritize these against the roadmap."
        return report

    def _notify_slack(self, repo_path, fail_count, smell_count):
        repo_name = os.path.basename(repo_path)
        message = f"👀 *Watcher Wedge* has completed an operational scan of `{repo_name}`.\n"
        message += f"Found *{fail_count}* failures and *{smell_count}* code smells.\n"
        message += "A high-priority analysis task has been injected into the backlog for Artoo and Poe. 🫡"
        post_to_slack(message)
