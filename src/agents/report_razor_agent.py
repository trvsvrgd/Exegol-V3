import os
import json
import datetime
from tools.gmail_tool import send_gmail_message


class ReportRazorAgent:
    """Composes a weekly fleet summary email covering key metrics,
    progress highlights, and issues across the entire agent fleet.

    Delivers a concise 1-5 minute read to travisvreugdenhil@gmail.com
    every week, giving the operator a clear picture of what happened."""

    def __init__(self, llm_client):
        self.llm_client = llm_client
        self.name = "ReportRazorAgent"
        self.max_steps = 10
        self.tools = ["gmail_api", "interaction_log_reader"]
        self.report_email = "travisvreugdenhil@gmail.com"
        self.success_metrics = {
            "weekly_email_delivered": {
                "description": "Percentage of weeks with the summary email delivered on time",
                "target": "100%",
                "current": None
            },
            "all_agents_covered": {
                "description": "Every registered agent appears in the weekly summary",
                "target": "100%",
                "current": None
            },
            "issues_surfaced": {
                "description": "All agents with error rate >10% are flagged under Issues",
                "target": "100%",
                "current": None
            },
            "read_time_minutes": {
                "description": "Email body stays within the 1-5 minute read target",
                "target": "1-5 min",
                "current": None
            }
        }
        self.system_prompt = self.llm_client.generate_system_prompt(self)


    # ------------------------------------------------------------------
    # Interaction log helpers
    # ------------------------------------------------------------------

    def _load_interaction_logs(self, repo_paths: list) -> list:
        """Load the last 7 days of agent interaction logs across multiple repos."""
        seven_days_ago = datetime.datetime.now() - datetime.timedelta(days=7)
        entries: list = []

        for repo_path in repo_paths:
            logs_dir = os.path.join(repo_path, ".exegol", "interaction_logs")
            if not os.path.isdir(logs_dir):
                print(f"[{self.name}] No interaction_logs directory found at {logs_dir}.")
                continue

            for filename in sorted(os.listdir(logs_dir)):
                if not filename.endswith(".json"):
                    continue
                filepath = os.path.join(logs_dir, filename)
                try:
                    with open(filepath, "r", encoding="utf-8") as f:
                        data = json.load(f)
                        if isinstance(data, list):
                            for entry in data:
                                ts = datetime.datetime.fromisoformat(entry.get("timestamp", ""))
                                if ts >= seven_days_ago:
                                    entry["_repo_path"] = repo_path
                                    entries.append(entry)
                        elif isinstance(data, dict):
                            ts = datetime.datetime.fromisoformat(data.get("timestamp", ""))
                            if ts >= seven_days_ago:
                                data["_repo_path"] = repo_path
                                entries.append(data)
                except Exception as e:
                    print(f"[{self.name}] Skipping log file {filename}: {e}")

        return entries

    def _load_repo_backlogs(self, repo_paths: list) -> dict:
        """Load backlog.json for all provided repositories."""
        backlogs = {}
        for repo_path in repo_paths:
            backlog_path = os.path.join(repo_path, ".exegol", "backlog.json")
            if os.path.exists(backlog_path):
                try:
                    with open(backlog_path, "r", encoding="utf-8") as f:
                        backlogs[repo_path] = json.load(f)
                except Exception as e:
                    print(f"[{self.name}] Error loading backlog.json at {repo_path}: {e}")
            else:
                backlogs[repo_path] = []
        return backlogs


    # ------------------------------------------------------------------
    # Fleet-level metrics
    # ------------------------------------------------------------------

    def _compute_fleet_metrics(self, logs: list, registry: dict) -> dict:
        """Aggregate key fleet-wide metrics from the past week's logs."""

        total_runs = len(logs)
        total_errors = sum(len(e.get("errors", [])) for e in logs)
        total_steps = sum(e.get("steps_used", 0) for e in logs)
        total_duration = sum(e.get("duration_seconds", 0) for e in logs)
        successes = sum(1 for e in logs if e.get("outcome") == "success")

        return {
            "total_runs": total_runs,
            "total_errors": total_errors,
            "total_steps_consumed": total_steps,
            "total_duration_seconds": total_duration,
            "success_rate": f"{(successes / total_runs * 100):.1f}%" if total_runs else "N/A",
            "avg_steps_per_run": round(total_steps / total_runs, 1) if total_runs else 0,
            "avg_duration_per_run_sec": round(total_duration / total_runs, 1) if total_runs else 0,
            "active_agents": len({e.get("agent_id") for e in logs}),
            "registered_agents": len(registry)
        }

    # ------------------------------------------------------------------
    # Per-agent breakdown
    # ------------------------------------------------------------------

    def _per_agent_summary(self, logs: list, registry: dict) -> list:
        """Build a per-agent summary with runs, success rate, and highlights."""

        stats: dict = {}
        tasks: dict = {}
        for entry in logs:
            aid = entry.get("agent_id", "unknown")
            if aid not in stats:
                stats[aid] = {"runs": 0, "successes": 0, "errors": 0,
                              "steps": 0, "duration": 0}
            stats[aid]["runs"] += 1
            stats[aid]["steps"] += entry.get("steps_used", 0)
            stats[aid]["duration"] += entry.get("duration_seconds", 0)
            stats[aid]["errors"] += len(entry.get("errors", []))
            if entry.get("outcome") == "success":
                stats[aid]["successes"] += 1
            # Collect task summaries for progress section
            task = entry.get("task_summary", "")
            if task:
                tasks.setdefault(aid, []).append(task)

        summaries = []
        for agent_id, details in registry.items():
            agent_class = details.get("class", agent_id)
            s = stats.get(agent_id)
            if s and s["runs"] > 0:
                success_pct = s["successes"] / s["runs"] * 100
                error_rate = s["errors"] / s["runs"] * 100
                recent_tasks = tasks.get(agent_id, [])[-3:]  # last 3 tasks
                summaries.append({
                    "agent": agent_class,
                    "runs": s["runs"],
                    "success_rate": f"{success_pct:.0f}%",
                    "error_rate": f"{error_rate:.0f}%",
                    "total_steps": s["steps"],
                    "avg_duration_sec": round(s["duration"] / s["runs"], 1),
                    "recent_tasks": recent_tasks,
                    "status": "⚠️ ISSUE" if error_rate > 10 else "✅ OK"
                })
            else:
                summaries.append({
                    "agent": agent_class,
                    "runs": 0,
                    "success_rate": "N/A",
                    "error_rate": "N/A",
                    "total_steps": 0,
                    "avg_duration_sec": 0,
                    "recent_tasks": [],
                    "status": "💤 IDLE"
                })

        return summaries

    # ------------------------------------------------------------------
    # Repo-level progress
    # ------------------------------------------------------------------

    def _per_repo_summary(self, logs: list, backlogs: dict) -> list:
        """Build a progress summary for each active repository."""
        repo_tasks = {}
        for entry in logs:
            rpath = entry.get("_repo_path")
            if rpath:
                task = entry.get("task_summary", "")
                if task and entry.get("outcome") == "success":
                    repo_tasks.setdefault(rpath, []).append(task)
        
        summaries = []
        for rpath, blog in backlogs.items():
            repo_name = os.path.basename(rpath)
            pending = sum(1 for t in blog if t.get("status") in ["pending_prioritization", "backlogged", "todo"])
            in_progress = sum(1 for t in blog if t.get("status") in ["in_progress", "active"])
            completed = sum(1 for t in blog if t.get("status") in ["done", "completed"])

            recent_successes = repo_tasks.get(rpath, [])[-5:]
            
            summaries.append({
                "repo_name": repo_name,
                "repo_path": rpath,
                "pending": pending,
                "in_progress": in_progress,
                "completed": completed,
                "total_backlog": len(blog),
                "recent_successes": recent_successes
            })

        return summaries

    # ------------------------------------------------------------------
    # Issue detection
    # ------------------------------------------------------------------

    def _detect_issues(self, agent_summaries: list) -> list:
        """Surface agents whose error rate exceeds 10% or that were idle."""
        issues = []
        for a in agent_summaries:
            if a["status"] == "⚠️ ISSUE":
                issues.append({
                    "agent": a["agent"],
                    "problem": f"Error rate {a['error_rate']} across {a['runs']} runs",
                    "recommendation": "Review recent logs, add retry logic or input validation."
                })
            elif a["status"] == "💤 IDLE":
                issues.append({
                    "agent": a["agent"],
                    "problem": "No activity recorded this week",
                    "recommendation": "Verify wake word routing and that logs are being emitted."
                })
        return issues

    # ------------------------------------------------------------------
    # Email composition
    # ------------------------------------------------------------------

    def _compose_email(self, fleet_metrics: dict, agent_summaries: list,
                       issues: list, repo_summaries: list) -> dict:
        """Build a polished HTML email for the weekly fleet summary."""

        now = datetime.datetime.now()
        week_start = (now - datetime.timedelta(days=7)).strftime("%b %d")
        week_end = now.strftime("%b %d, %Y")

        # Fleet KPIs row
        kpi_html = f"""\
<table style="width:100%;border-collapse:collapse;margin-bottom:20px;">
<tr style="background:#2a2a4a;">
  <td style="padding:12px;text-align:center;border-right:1px solid #444;">
    <div style="font-size:28px;font-weight:bold;color:#00d4ff;">{fleet_metrics['total_runs']}</div>
    <div style="font-size:12px;color:#aaa;">Total Runs</div>
  </td>
  <td style="padding:12px;text-align:center;border-right:1px solid #444;">
    <div style="font-size:28px;font-weight:bold;color:#51cf66;">{fleet_metrics['success_rate']}</div>
    <div style="font-size:12px;color:#aaa;">Success Rate</div>
  </td>
  <td style="padding:12px;text-align:center;border-right:1px solid #444;">
    <div style="font-size:28px;font-weight:bold;color:#ffd43b;">{fleet_metrics['active_agents']}/{fleet_metrics['registered_agents']}</div>
    <div style="font-size:12px;color:#aaa;">Active Agents</div>
  </td>
  <td style="padding:12px;text-align:center;">
    <div style="font-size:28px;font-weight:bold;color:#ff6b6b;">{fleet_metrics['total_errors']}</div>
    <div style="font-size:12px;color:#aaa;">Total Errors</div>
  </td>
</tr>
</table>"""

        # Per-agent table
        agent_rows = "\n".join(
            f"<tr>"
            f"<td style='padding:6px 12px;border-bottom:1px solid #333'>{a['status']}</td>"
            f"<td style='padding:6px 12px;border-bottom:1px solid #333'>"
            f"<strong>{a['agent']}</strong></td>"
            f"<td style='padding:6px 12px;border-bottom:1px solid #333;text-align:center'>"
            f"{a['runs']}</td>"
            f"<td style='padding:6px 12px;border-bottom:1px solid #333;text-align:center'>"
            f"{a['success_rate']}</td>"
            f"<td style='padding:6px 12px;border-bottom:1px solid #333;text-align:center'>"
            f"{a['total_steps']}</td>"
            f"</tr>"
            for a in agent_summaries
        )

        # Progress highlights (agents with recent tasks)
        progress_items = ""
        for a in agent_summaries:
            if a["recent_tasks"]:
                tasks_list = "".join(f"<li>{t}</li>" for t in a["recent_tasks"])
                progress_items += (
                    f"<li><strong>{a['agent']}</strong><ul>{tasks_list}</ul></li>"
                )
        if not progress_items:
            progress_items = "<li>No task summaries recorded this week.</li>"

        # Repo Progress section
        repo_items = ""
        for r in repo_summaries:
            tasks_list = "".join(f"<li>{t}</li>" for t in r["recent_successes"])
            if not tasks_list:
                tasks_list = "<li>No recent completed tasks.</li>"
            
            stats = (f"<span style='color:#ffd43b;'>{r['pending']}</span> pending, "
                     f"<span style='color:#51cf66;'>{r['in_progress']}</span> acting, "
                     f"<span style='color:#00d4ff;'>{r['completed']}</span> done")

            repo_items += (
                f"<div style='margin-bottom:16px;background:#2a2a4a;padding:12px;border-left:4px solid #a970ff;'>"
                f"<h4 style='margin:0 0 8px 0;'>📁 {r['repo_name']}</h4>"
                f"<div style='font-size:12px;color:#aaa;margin-bottom:8px;'>Backlog: {stats} | Total: {r['total_backlog']}</div>"
                f"<ul style='margin:0;padding-left:16px;'>{tasks_list}</ul>"
                f"</div>"
            )
        
        repo_section = f"""\
<h3 style="color:#a970ff;">📂 Repository Progress</h3>
{repo_items}""" if repo_items else ""

        # Issues section
        if issues:
            issues_html = "\n".join(
                f"<tr>"
                f"<td style='padding:6px 12px;border-bottom:1px solid #533;color:#ff6b6b'>"
                f"<strong>{i['agent']}</strong></td>"
                f"<td style='padding:6px 12px;border-bottom:1px solid #533'>"
                f"{i['problem']}</td>"
                f"<td style='padding:6px 12px;border-bottom:1px solid #533;color:#ffd43b'>"
                f"{i['recommendation']}</td>"
                f"</tr>"
                for i in issues
            )
            issues_section = f"""\
<h3 style="color:#ff6b6b;">🚨 Issues &amp; Warnings</h3>
<table style="width:100%;border-collapse:collapse;">
<tr style="background:#3a1a1a;">
  <th style="padding:8px 12px;text-align:left;">Agent</th>
  <th style="padding:8px 12px;text-align:left;">Problem</th>
  <th style="padding:8px 12px;text-align:left;">Recommendation</th>
</tr>
{issues_html}
</table>"""
        else:
            issues_section = """\
<h3 style="color:#51cf66;">✅ No Issues Detected</h3>
<p>All agents operated within normal parameters this week.</p>"""

        html_body = f"""\
<html>
<body style="font-family:Arial,sans-serif;background:#1a1a2e;color:#e0e0e0;padding:24px;">
<h2 style="color:#00d4ff;">📊 Exegol Weekly Fleet Summary</h2>
<p style="color:#aaa;">Week of {week_start} – {week_end}</p>

<h3 style="color:#00d4ff;">🔑 Key Metrics</h3>
{kpi_html}

<h3 style="color:#51cf66;">📈 Agent Activity</h3>
<table style="width:100%;border-collapse:collapse;">
<tr style="background:#2a2a4a;">
  <th style="padding:8px 12px;text-align:left;">Status</th>
  <th style="padding:8px 12px;text-align:left;">Agent</th>
  <th style="padding:8px 12px;text-align:center;">Runs</th>
  <th style="padding:8px 12px;text-align:center;">Success</th>
  <th style="padding:8px 12px;text-align:center;">Steps</th>
</tr>
{agent_rows}
</table>

<h3 style="color:#ffd43b;">🏗️ Progress Highlights</h3>
<ul>{progress_items}</ul>

{repo_section}

{issues_section}

<hr style="border-color:#333;">
<p style="color:#666;font-size:12px;">
  Sent by ReportRazorAgent · Exegol v3 Orchestrator
</p>
</body>
</html>"""

        return {
            "to": self.report_email,
            "subject": (
                f"📊 Exegol Fleet Summary — "
                f"Week {now.isocalendar()[1]} ({week_start} – {week_end})"
            ),
            "body_html": html_body
        }

    # ------------------------------------------------------------------
    # Validation
    # ------------------------------------------------------------------

    def _validate_report(self, agent_summaries: list,
                         registry: dict) -> bool:
        """Ensure every registered agent appears in the summary."""
        reported_agents = {a["agent"] for a in agent_summaries}
        registry_classes = {v["class"] for v in registry.values()}

        if not registry_classes.issubset(reported_agents):
            missing = registry_classes - reported_agents
            print(f"[{self.name}] VALIDATION FAIL — missing agents: {missing}")
            return False

        print(f"[{self.name}] Validation passed — all {len(registry)} agents covered.")
        return True

    # ------------------------------------------------------------------
    # Main execution
    # ------------------------------------------------------------------

    def execute(self, handoff):
        """Run the weekly fleet summary cycle.

        Accepts a HandoffContext — no prior session memory required.
        All state is read fresh from the filesystem.
        """
        from agents.registry import AGENT_REGISTRY

        repo_path = handoff.repo_path
        print(f"[{self.name}] Session {handoff.session_id} — weekly fleet summary starting.")

        # 0. Load priority.json for all repos
        priority_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'config', 'priority.json')
        repo_paths = [repo_path]
        if os.path.exists(priority_path):
            try:
                with open(priority_path, 'r') as f:
                    pconfig = json.load(f)
                repos = pconfig.get("repositories", [])
                repo_paths = [r["repo_path"] for r in repos if r.get("repo_path")]
            except Exception as e:
                print(f"[{self.name}] Error reading priority.json: {e}")

        # 1. Load data from all repositories
        logs = self._load_interaction_logs(repo_paths)
        print(f"[{self.name}] Loaded {len(logs)} interaction log entries from {len(repo_paths)} repos in 7 days.")
        
        backlogs = self._load_repo_backlogs(repo_paths)

        # 2. Fleet-level metrics
        fleet_metrics = self._compute_fleet_metrics(logs, AGENT_REGISTRY)
        print(f"[{self.name}] Fleet: {fleet_metrics['total_runs']} runs, "
              f"{fleet_metrics['success_rate']} success rate, "
              f"{fleet_metrics['active_agents']}/{fleet_metrics['registered_agents']} agents active.")

        # 3. Per-agent breakdown
        agent_summaries = self._per_agent_summary(logs, AGENT_REGISTRY)
        print(f"[{self.name}] Generated summaries for {len(agent_summaries)} agents.")

        # 4. Issue detection
        issues = self._detect_issues(agent_summaries)
        if issues:
            print(f"[{self.name}] ⚠ {len(issues)} issues detected.")
        else:
            print(f"[{self.name}] No issues detected.")

        # 5. Repo Summaries
        repo_summaries = self._per_repo_summary(logs, backlogs)

        # 6. Validate
        if not self._validate_report(agent_summaries, AGENT_REGISTRY):
            return "Fleet summary failed validation. No email sent."

        # 7. Compose email
        email_payload = self._compose_email(fleet_metrics, agent_summaries, issues, repo_summaries)

        # 7. Persist report
        exegol_dir = os.path.join(repo_path, ".exegol")
        os.makedirs(exegol_dir, exist_ok=True)
        reports_dir = os.path.join(exegol_dir, "fleet_reports")
        os.makedirs(reports_dir, exist_ok=True)

        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        report_file = os.path.join(reports_dir, f"weekly_{timestamp}.json")

        report_data = {
            "generated_at": timestamp,
            "fleet_metrics": fleet_metrics,
            "agent_summaries": [
                {k: v for k, v in a.items()} for a in agent_summaries
            ],
            "repo_summaries": [
                {k: v for k, v in r.items()} for r in repo_summaries
            ],
            "issues": issues,
            "email_subject": email_payload["subject"],
            "email_to": email_payload["to"]
        }
        with open(report_file, "w", encoding="utf-8") as f:
            json.dump(report_data, f, indent=4)

        print(f"[{self.name}] Report persisted to {report_file}")

        # 8. Send email via real gmail_api tool
        print(f"[{self.name}] Sending email to {self.report_email}...")
        
        # Create a simple plain-text fallback
        text_body = (
            f"Exegol Weekly Fleet Summary\n"
            f"Runs: {fleet_metrics['total_runs']}\n"
            f"Success: {fleet_metrics['success_rate']}\n"
            f"Errors: {fleet_metrics['total_errors']}\n"
            f"Please view in an HTML-compatible email client for full details."
        )
        
        result = send_gmail_message(
            to=self.report_email,
            subject=email_payload["subject"],
            body=text_body,
            body_html=email_payload["body_html"]
        )
        print(f"[{self.name}] {result}")

        return (
            f"Weekly fleet summary generated and emailed. "
            f"{fleet_metrics['total_runs']} total runs, "
            f"{fleet_metrics['success_rate']} success rate, "
            f"{len(issues)} issues flagged. "
            f"Report saved: {report_file}"
        )
