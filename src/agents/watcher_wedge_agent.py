import os
import json
import time
import datetime
import re
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
2. Audit Codebase: Look for 'smells' like hardcoded credentials, unhandled fetch calls, or unverified implementations that require attention.
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
            
            # 2. Scan for Code Smells (TODOS, Stubbed code, etc)
            audit_findings = analyze_repository(repo_path)
            
            # 2b. Scan for Security Vulnerabilities (Phase 3 Integration)
            print(f"[{self.name}] Scanning for security vulnerabilities...")
            security_findings = scan_for_security_vulnerabilities(repo_path)
            
            # 3. Targeted Scan for the specific issue the user mentioned (fetch without catch)
            targeted_issues = self._targeted_code_scan(repo_path)
            
            # 4. Consolidate findings
            all_issues = audit_findings + security_findings + targeted_issues
            
            if not failures and not all_issues:
                print(f"[{self.name}] No operational issues or code smells detected. Wedge standing down.")
                # We still log the interaction but as a 'no-op' success
                log_interaction(
                    agent_id=self.name,
                    outcome="success",
                    task_summary="Wedge completed health check. No issues detected.",
                    repo_path=repo_path,
                    steps_used=1,
                    duration_seconds=time.time() - start_time,
                    session_id=handoff.session_id,
                    metrics={"issues_detected": 0, "backlog_injections": 0}
                )
                return "No operational issues or code smells detected. Wedge standing down."

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
        """Looks for specific patterns like unhandled fetch calls or hardcoded keys across the codebase."""
        print(f"[{self.name}] Performing deep-dive scan for unhandled fetch calls and hardcoded secrets...")
        findings = []
        src_dir = os.path.join(repo_path, "src")
        
        if not os.path.exists(src_dir):
            return findings

        # Patterns for detection
        fetch_pattern = re.compile(r"fetch\(", re.IGNORECASE)
        catch_pattern = re.compile(r"\.catch\(", re.IGNORECASE)
        key_pattern = re.compile(r"(API_KEY|SECRET_KEY|ACCESS_TOKEN)\s*=\s*['\"][a-zA-Z0-9\-_]{16,}['\"]", re.IGNORECASE)

        for root, _, files in os.walk(src_dir):
            for file in files:
                if not file.endswith(('.tsx', '.ts', '.js', '.jsx', '.py')):
                    continue
                
                file_path = os.path.join(root, file)
                rel_path = os.path.relpath(file_path, repo_path)
                
                try:
                    with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                        lines = f.readlines()
                        content = "".join(lines)
                        
                        # 1. Check for fetch without catch
                        if fetch_pattern.search(content) and not catch_pattern.search(content):
                            findings.append({
                                "task": f"Add error handling to fetch calls in {rel_path}",
                                "category": "stability",
                                "context": "Found fetch() without .catch() block. This causes silent failures."
                            })
                        
                        # 2. Check for hardcoded keys line by line
                        for i, line in enumerate(lines, 1):
                            if key_pattern.search(line):
                                findings.append({
                                    "task": f"Audit hardcoded API key in {rel_path}:L{i}",
                                    "category": "security",
                                    "context": line.strip()
                                })
                except Exception as e:
                    print(f"[{self.name}] Error scanning {rel_path}: {e}")
                    
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
