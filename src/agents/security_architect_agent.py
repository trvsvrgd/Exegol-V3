import os
import json
import re
import datetime
import time
from tools.fleet_logger import log_interaction
from tools.backlog_manager import BacklogManager


class SecurityArchitectAgent:
    """Evaluates repository architecture for security weaknesses, zero-day vulnerabilities,
    and architectural gaps. Submissions to the backlog are the primary success metric,
    measured alongside zero-day pattern detection in the codebase.

    Triggered on-demand or as part of a regular security cadence.
    Writes a structured security report and adds findings to the backlog
    for Developer Dex and the broader fleet to action.
    """

    def __init__(self, llm_client):
        self.llm_client = llm_client
        self.name = "SecurityArchitectAgent"
        self.max_steps = 20
        self._steps_used = 0
        self.tools = ["repo_scanner", "cve_lookup", "backlog_writer", "architecture_reviewer"]
        self.success_metrics = {
            "backlog_submissions": {
                "description": "Number of security findings submitted to backlog per scan",
                "target": ">=3",
                "current": None
            },
            "zero_day_patterns_detected": {
                "description": "Number of known zero-day vulnerability patterns detected in the repo",
                "target": "0",
                "current": None
            },
            "critical_findings": {
                "description": "Number of CRITICAL severity findings per scan",
                "target": "0",
                "current": None
            },
            "architecture_gaps": {
                "description": "Number of structural security gaps identified in the agent architecture",
                "target": "0",
                "current": None
            }
        }
        self.system_prompt = self.llm_client.generate_system_prompt(self)

    # ------------------------------------------------------------------
    # Zero-Day Pattern Detection
    # ------------------------------------------------------------------

    def _scan_for_zero_day_patterns(self, repo_path: str) -> list:
        """Scans source files for patterns matching known zero-day vulnerability categories.

        Covers: prompt injection, arbitrary code execution, path traversal,
        hardcoded secrets, insecure deserialization, and SSRF vectors.
        """
        findings = []

        # Known dangerous patterns — each maps to a CWE and severity
        VULN_PATTERNS = [
            {
                "id": "SEC-ZD-001",
                "name": "Prompt Injection Vector",
                "cwe": "CWE-77: Improper Neutralization of Special Elements",
                "severity": "CRITICAL",
                "patterns": [r"f\".*{.*prompt.*}\"|format.*user.*input|\.format\(.*request"],
                "description": "Unsanitized user input is interpolated directly into LLM prompts, enabling prompt injection.",
                "recommendation": "Sanitize all user inputs before injecting into prompts. Use a dedicated input validation layer."
            },
            {
                "id": "SEC-ZD-002",
                "name": "Arbitrary Code Execution via eval/exec",
                "cwe": "CWE-78: OS Command Injection / CWE-94: Code Injection",
                "severity": "CRITICAL",
                "case_sensitive": True,
                "patterns": [r"\beval\s*\(", r"\bexec\s*\(", r"subprocess\.call\(.*shell\s*=\s*True"],
                "description": "Use of eval(), exec(), or subprocess with shell=True can allow arbitrary code execution.",
                "recommendation": "Eliminate eval/exec. Use subprocess with shell=False and explicit argument lists."
            },
            {
                "id": "SEC-ZD-003",
                "name": "Path Traversal Vulnerability",
                "cwe": "CWE-22: Path Traversal",
                "severity": "HIGH",
                "patterns": [r"os\.path\.join\(.*request|open\(.*\+.*|open\(.*format\("],
                "description": "File paths are constructed from unvalidated input, enabling directory traversal attacks.",
                "recommendation": "Validate and sanitize all file paths. Use os.path.realpath() and assert paths remain within allowed directories."
            },
            {
                "id": "SEC-ZD-004",
                "name": "Hardcoded Secrets / Credentials",
                "cwe": "CWE-798: Use of Hard-coded Credentials",
                "severity": "CRITICAL",
                "patterns": [
                    r"(password|secret|api_key|token|passwd)\s*=\s*['\"][^'\"]{6,}['\"]",
                    r"Bearer\s+[a-zA-Z0-9\-_\.]+",
                    r"sk-[a-zA-Z0-9]{20,}"
                ],
                "description": "Credentials or secrets are hardcoded in source files and may be exposed via version control.",
                "recommendation": "Move all secrets to environment variables or a secrets manager. Rotate any exposed credentials immediately."
            },
            {
                "id": "SEC-ZD-005",
                "name": "Insecure Deserialization",
                "cwe": "CWE-502: Deserialization of Untrusted Data",
                "severity": "HIGH",
                "patterns": [r"\bpickle\.loads?\(", r"\byaml\.load\s*\([^)]*\)(?!\s*,\s*Loader=yaml\.SafeLoader)"],
                "description": "Unsafe deserialization methods (pickle.load, yaml.load without SafeLoader) can execute arbitrary code.",
                "recommendation": "Replace pickle with json. Use yaml.safe_load() instead of yaml.load()."
            },
            {
                "id": "SEC-ZD-006",
                "name": "Server-Side Request Forgery (SSRF) Vector",
                "cwe": "CWE-918: Server-Side Request Forgery",
                "severity": "HIGH",
                "patterns": [r"requests\.(get|post|put)\s*\(.*(?:url|endpoint|target)"],
                "description": "HTTP requests are made to URLs derived from user-controllable data, enabling SSRF attacks.",
                "recommendation": "Validate and whitelist allowed URLs/domains before making outbound HTTP requests."
            },
            {
                "id": "SEC-ZD-007",
                "name": "Unsafe Temporary File Handling",
                "cwe": "CWE-377: Insecure Temporary File",
                "severity": "MEDIUM",
                "patterns": [r"tempfile\.mk(?:temp|stemp)\(", r"open\s*\(\s*['\"]\/tmp\/"],
                "description": "Temporary files created insecurely can be exploited via symlink attacks or race conditions.",
                "recommendation": "Use tempfile.NamedTemporaryFile with delete=True and context managers."
            },
            {
                "id": "SEC-ZD-008",
                "name": "Missing Input Validation on LLM JSON Parse",
                "cwe": "CWE-20: Improper Input Validation",
                "severity": "HIGH",
                "patterns": [r"json\.loads?\(.*llm|json\.loads?\(.*response|json\.loads?\(.*output"],
                "description": "LLM outputs are deserialized without validation, enabling crafted payloads to corrupt state.",
                "recommendation": "Validate all LLM JSON responses against a schema before using them to drive execution."
            }
        ]

        src_dir = os.path.join(repo_path, "src")
        if not os.path.isdir(src_dir):
            print(f"[{self.name}] No src/ directory found — skipping code scan.")
            return findings

        scanned_files = 0
        for root, _, files in os.walk(src_dir):
            for filename in files:
                if not filename.endswith(".py"):
                    continue

                # Skip self to avoid false positives from scanning our own pattern definitions
                if "security_architect_agent" in filename:
                    continue

                file_path = os.path.join(root, filename)
                rel_path = os.path.relpath(file_path, repo_path)
                scanned_files += 1

                try:
                    with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
                        content = f.read()
                        lines = content.splitlines()

                    for vuln in VULN_PATTERNS:
                        case_flags = 0 if vuln.get("case_sensitive") else re.IGNORECASE
                        for pattern_str in vuln["patterns"]:
                            try:
                                matches = list(re.finditer(pattern_str, content, case_flags))
                            except re.error:
                                continue

                            for match in matches:
                                # Find line number of match
                                line_num = content[:match.start()].count("\n") + 1
                                line_text = lines[line_num - 1].strip() if line_num <= len(lines) else ""

                                findings.append({
                                    "vuln_id": vuln["id"],
                                    "name": vuln["name"],
                                    "cwe": vuln["cwe"],
                                    "severity": vuln["severity"],
                                    "file": rel_path,
                                    "line": line_num,
                                    "evidence": line_text[:200],
                                    "description": vuln["description"],
                                    "recommendation": vuln["recommendation"]
                                })
                                # Only report first match per vuln per file to reduce noise
                                break

                except Exception as e:
                    print(f"[{self.name}] Could not scan {rel_path}: {e}")

        print(f"[{self.name}] Zero-day scan complete. Scanned {scanned_files} Python files.")
        return findings

    # ------------------------------------------------------------------
    # Architectural Gap Analysis
    # ------------------------------------------------------------------

    def _evaluate_architecture(self, repo_path: str) -> list:
        """Evaluates the agent fleet architecture against security best practices.

        Checks for: missing auth controls, absence of rate limiting, 
        no secrets management, lack of audit logging, missing RBAC,
        unsecured inter-agent communication, and missing input sanitization.
        """
        gaps = []
        src_dir = os.path.join(repo_path, "src")
        tools_dir = os.path.join(src_dir, "tools")
        agents_dir = os.path.join(src_dir, "agents")
        exegol_dir = os.path.join(repo_path, ".exegol")

        def file_exists_in(*paths) -> bool:
            return any(os.path.exists(p) for p in paths)

        def any_file_contains(directory: str, keyword: str) -> bool:
            if not os.path.isdir(directory):
                return False
            for fname in os.listdir(directory):
                fpath = os.path.join(directory, fname)
                if os.path.isfile(fpath) and fname.endswith(".py"):
                    try:
                        with open(fpath, "r", encoding="utf-8", errors="ignore") as f:
                            if keyword.lower() in f.read().lower():
                                return True
                    except Exception:
                        pass
            return False

        # 1. No Authentication / Authorization Layer
        has_auth = any_file_contains(tools_dir, "authenticate") or \
                   any_file_contains(src_dir, "authorization") or \
                   file_exists_in(os.path.join(tools_dir, "auth_tool.py"), os.path.join(src_dir, "auth.py"))
        if not has_auth:
            gaps.append({
                "id": "SEC-ARCH-001",
                "name": "Missing Authentication & Authorization Layer",
                "severity": "CRITICAL",
                "category": "Access Control",
                "description": "No authentication or authorization controls are in place. Any caller can trigger agent execution or read sensitive outputs without identity verification.",
                "recommendation": "Implement an API key or JWT-based authentication layer in the orchestrator. Add role-based access control (RBAC) to restrict which agents can perform which operations."
            })

        # 2. No Rate Limiting
        has_rate_limit = any_file_contains(tools_dir, "rate_limit") or any_file_contains(src_dir, "throttle")
        if not has_rate_limit:
            gaps.append({
                "id": "SEC-ARCH-002",
                "name": "No Rate Limiting on Agent Invocations",
                "severity": "HIGH",
                "category": "Denial of Service",
                "description": "Agents can be triggered at unlimited frequency. A malicious or runaway process could exhaust LLM API quotas, incur unbounded costs, or trigger external service bans.",
                "recommendation": "Implement per-agent rate limiting in the SessionManager. Add configurable cooldown periods between executions of the same agent."
            })

        # 3. Secrets Not Managed via Env (check .env usage)
        env_file = os.path.join(repo_path, ".env")
        env_in_gitignore = False
        gitignore = os.path.join(repo_path, ".gitignore")
        if os.path.exists(gitignore):
            with open(gitignore, "r", encoding="utf-8", errors="ignore") as f:
                gitignore_content = f.read()
            env_in_gitignore = ".env" in gitignore_content
        if not env_in_gitignore:
            gaps.append({
                "id": "SEC-ARCH-003",
                "name": ".env File Not Excluded from Version Control",
                "severity": "CRITICAL",
                "category": "Secrets Management",
                "description": ".gitignore does not explicitly exclude the .env file. Credentials committed to git history are permanently exposed, even if later deleted from the working tree.",
                "recommendation": "Add '.env', '*.env', 'token.json', and 'credentials.json' to .gitignore immediately. Rotate any secrets that may have been committed."
            })

        # 4. No Centralized Audit Log
        has_audit_log = any_file_contains(tools_dir, "audit") or \
                        file_exists_in(os.path.join(tools_dir, "audit_logger.py"))
        if not has_audit_log:
            gaps.append({
                "id": "SEC-ARCH-004",
                "name": "No Centralized Security Audit Log",
                "severity": "HIGH",
                "category": "Audit & Compliance",
                "description": "The fleet_logger captures operational metrics but lacks a tamper-resistant security audit trail. Security events (e.g., auth failures, file deletions, credential access) are not logged separately.",
                "recommendation": "Create a dedicated security_audit_log.json or append-only event stream. Log all security-relevant events with actor, timestamp, action, and outcome fields."
            })

        # 5. Inter-Agent Communication Not Validated
        has_handoff_validation = any_file_contains(src_dir, "validate_handoff") or \
                                  any_file_contains(src_dir, "signature")
        if not has_handoff_validation:
            gaps.append({
                "id": "SEC-ARCH-005",
                "name": "Unsigned/Unvalidated Inter-Agent Handoffs",
                "severity": "HIGH",
                "category": "Trust Boundary",
                "description": "HandoffContext objects passed between agents are not cryptographically signed or validated. A compromised agent could forge a handoff to escalate privileges or redirect execution flow.",
                "recommendation": "Add a HMAC signature field to HandoffContext. The SessionManager should validate the signature before spawning any agent session."
            })

        # 6. No Input Sanitization Module
        has_sanitizer = file_exists_in(
            os.path.join(tools_dir, "input_sanitizer.py"),
            os.path.join(tools_dir, "sanitizer.py")
        ) or any_file_contains(tools_dir, "sanitize")
        if not has_sanitizer:
            gaps.append({
                "id": "SEC-ARCH-006",
                "name": "No Input Sanitization Layer",
                "severity": "HIGH",
                "category": "Injection Defense",
                "description": "Agent inputs (from active_prompt.md, backlog.json) are used directly without a dedicated sanitization pass. This leaves the fleet vulnerable to prompt injection and data exfiltration via crafted inputs.",
                "recommendation": "Implement a reusable input_sanitizer tool that strips control characters, validates expected schemas, and detects prompt injection markers before any agent processes external data."
            })

        # 7. Backlog Not Schema Validated Before Execution
        has_schema_validation = any_file_contains(src_dir, "schema_validate") or \
                                 any_file_contains(tools_dir, "schema")
        if not has_schema_validation:
            gaps.append({
                "id": "SEC-ARCH-007",
                "name": "Backlog Tasks Not Schema-Validated Before Execution",
                "severity": "MEDIUM",
                "category": "Data Integrity",
                "description": "Tasks from backlog.json are consumed and acted upon without validating their structure. A malformed or adversarially crafted task could crash an agent or trigger unintended behavior.",
                "recommendation": "Define a JSON Schema for backlog task entries. Validate every task against this schema in ProductPoeAgent before writing to active_prompt.md."
            })

        # 8. No Network Egress Controls (Agents can make arbitrary HTTP calls)
        has_egress_control = any_file_contains(tools_dir, "allowed_domains") or \
                              any_file_contains(tools_dir, "egress")
        if not has_egress_control:
            gaps.append({
                "id": "SEC-ARCH-008",
                "name": "No Network Egress Allowlist",
                "severity": "MEDIUM",
                "category": "Network Security",
                "description": "Agents that make HTTP requests (gmail_tool, slack_tool, web_search) can access any network endpoint. A compromised prompt could exfiltrate data to an attacker-controlled server.",
                "recommendation": "Define an allowlist of permitted domains/IPs. Wrap all outbound HTTP calls through a controlled egress_filter tool that blocks non-allowlisted destinations."
            })

        print(f"[{self.name}] Architecture evaluation complete. Identified {len(gaps)} architectural gaps.")
        return gaps

    # ------------------------------------------------------------------
    # Backlog Integration
    # ------------------------------------------------------------------

    def _submit_to_backlog(self, repo_path: str, findings: list, gaps: list) -> int:
        """Submit all security findings and architectural gaps to the project backlog."""
        bm = BacklogManager(repo_path)
        added = 0

        # Deduplicate and add findings
        for finding in findings:
            task = {
                "id": f"sec_{finding['vuln_id'].lower().replace('-', '_')}",
                "summary": f"[{finding['severity']}] {finding['name']} \u2014 {finding['file']}:L{finding['line']}",
                "description": (
                    f"{finding['description']}\n\n"
                    f"**Evidence:** `{finding['evidence']}`\n\n"
                    f"**CWE:** {finding['cwe']}\n\n"
                    f"**Fix:** {finding['recommendation']}"
                ),
                "priority": "critical" if finding["severity"] == "CRITICAL" else "high" if finding["severity"] == "HIGH" else "medium",
                "type": "security_vulnerability",
                "status": "pending_prioritization",
                "source_requirement_id": finding["vuln_id"],
                "detected_by": self.name,
                "detected_at": datetime.datetime.now().isoformat()
            }
            if bm.add_task(task):
                added += 1

        for gap in gaps:
            task = {
                "id": f"sec_{gap['id'].lower().replace('-', '_')}",
                "summary": f"[{gap['severity']}] Security Architecture Gap: {gap['name']}",
                "description": (
                    f"{gap['description']}\n\n"
                    f"**Category:** {gap['category']}\n\n"
                    f"**Recommendation:** {gap['recommendation']}"
                ),
                "priority": "critical" if gap["severity"] == "CRITICAL" else "high" if gap["severity"] == "HIGH" else "medium",
                "type": "security_architecture",
                "status": "pending_prioritization",
                "source_requirement_id": gap["id"],
                "detected_by": self.name,
                "detected_at": datetime.datetime.now().isoformat()
            }
            if bm.add_task(task):
                added += 1

        print(f"[{self.name}] Submitted {added} new security tasks to backlog.")
        return added

    # ------------------------------------------------------------------
    # Report Generation
    # ------------------------------------------------------------------

    def _write_security_report(self, repo_path: str, findings: list, gaps: list, backlog_count: int) -> str:
        """Write a structured JSON security report to .exegol/security_reports/."""
        reports_dir = os.path.join(repo_path, ".exegol", "security_reports")
        os.makedirs(reports_dir, exist_ok=True)

        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        report_file = os.path.join(reports_dir, f"security_scan_{timestamp}.json")

        severity_counts = {}
        for f in findings:
            sev = f.get("severity", "UNKNOWN")
            severity_counts[sev] = severity_counts.get(sev, 0) + 1

        zero_day_count = len(findings)

        report = {
            "generated_at": datetime.datetime.now().isoformat(),
            "generated_by": self.name,
            "summary": {
                "zero_day_patterns_detected": zero_day_count,
                "architectural_gaps": len(gaps),
                "backlog_submissions": backlog_count,
                "severity_breakdown": severity_counts,
                "risk_score": self._compute_risk_score(findings, gaps)
            },
            "zero_day_findings": findings,
            "architectural_gaps": gaps
        }

        with open(report_file, "w", encoding="utf-8") as f:
            json.dump(report, f, indent=4)

        print(f"[{self.name}] Security report saved to {report_file}")
        return report_file

    def _compute_risk_score(self, findings: list, gaps: list) -> str:
        """Compute an overall risk score: CRITICAL > HIGH > MEDIUM > LOW."""
        all_severities = [f["severity"] for f in findings] + [g["severity"] for g in gaps]
        if "CRITICAL" in all_severities:
            return "CRITICAL"
        elif "HIGH" in all_severities:
            return "HIGH"
        elif "MEDIUM" in all_severities:
            return "MEDIUM"
        return "LOW"

    # ------------------------------------------------------------------
    # Main Execution
    # ------------------------------------------------------------------

    def execute(self, handoff):
        """Execute a full security architecture scan.

        Accepts a HandoffContext — no prior session memory required.
        All state is read fresh from the filesystem.
        """
        start_time = time.time()
        self._steps_used = 0
        repo_path = handoff.repo_path

        print(f"[{self.name}] Session {handoff.session_id} — initiating security architecture scan for: {repo_path}")

        try:
            # Step 1: Zero-Day Pattern Detection
            print(f"[{self.name}] [1/4] Scanning for zero-day vulnerability patterns...")
            findings = self._scan_for_zero_day_patterns(repo_path)
            self._steps_used += 1

            # Step 2: Architectural Gap Analysis
            print(f"[{self.name}] [2/4] Evaluating agent fleet architecture...")
            gaps = self._evaluate_architecture(repo_path)
            self._steps_used += 1

            # Step 3: Submit to Backlog
            print(f"[{self.name}] [3/4] Submitting findings to backlog...")
            backlog_count = self._submit_to_backlog(repo_path, findings, gaps)
            self._steps_used += 1

            # Step 4: Write Report
            print(f"[{self.name}] [4/4] Writing security report...")
            report_file = self._write_security_report(repo_path, findings, gaps, backlog_count)
            self._steps_used += 1

            duration = time.time() - start_time
            zero_day_count = len(findings)
            critical_count = sum(1 for f in (findings + gaps) if f.get("severity") == "CRITICAL")

            res = (
                f"Security scan complete. "
                f"Zero-day patterns detected: {zero_day_count}. "
                f"Architectural gaps: {len(gaps)}. "
                f"Backlog submissions: {backlog_count}. "
                f"Critical findings: {critical_count}. "
                f"Report: {report_file}"
            )

            log_interaction(
                agent_id=self.name,
                outcome="success",
                task_summary=res,
                repo_path=repo_path,
                steps_used=self._steps_used,
                duration_seconds=duration,
                session_id=handoff.session_id
            )

            # Chain to compliance agent if critical findings are present
            if critical_count > 0:
                self.next_agent_id = "compliance_cody"
                print(f"[{self.name}] Critical findings detected — chaining to ComplianceCody for regulatory review.")
            else:
                self.next_agent_id = None

            return res

        except Exception as e:
            duration = time.time() - start_time
            log_interaction(
                agent_id=self.name,
                outcome="failure",
                task_summary=f"Security scan failed: {str(e)}",
                repo_path=repo_path,
                steps_used=self._steps_used,
                duration_seconds=duration,
                errors=[str(e)],
                session_id=handoff.session_id
            )
            return f"[{self.name}] Error during security scan: {e}"
