import os
import json
import datetime
import importlib
from tools.gmail_tool import send_gmail_message
from tools.agent_introspection import introspect_agent


class ChiefOfStaffChewieAgent:
    """Oversees all agent operations, reviews reports, and provides high-level strategic feedback."""

    def __init__(self, llm_client):
        self.llm_client = llm_client
        self.name = "ChiefOfStaffChewieAgent"
        self.max_steps = 15
        self.tools = ["gmail_api", "interaction_log_reader", "agent_introspection"]
        self.report_email = "travisvreugdenhil@gmail.com"
        self.review_period_days = 7
        self.success_metrics = {
            "agents_reviewed": {
                "description": "Every registered agent receives a review each cycle",
                "target": "100%",
                "current": None
            },
            "underperformers_flagged": {
                "description": "All agents scoring C or below are flagged with mandates",
                "target": "100%",
                "current": None
            },
            "review_delivered_on_time": {
                "description": "Percentage of review cycles completed on schedule",
                "target": "100%",
                "current": None
            }
        }
        self.system_prompt = self.llm_client.generate_system_prompt(self)


    # ------------------------------------------------------------------
    # Interaction log loading
    # ------------------------------------------------------------------

    def _load_interaction_logs(self, repo_path: str) -> list:
        """Load the last N days of agent interaction logs."""
        logs_dir = os.path.join(repo_path, ".exegol", "interaction_logs")
        if not os.path.isdir(logs_dir):
            print(f"[{self.name}] No interaction_logs directory at {logs_dir}.")
            return []

        cutoff = datetime.datetime.now() - datetime.timedelta(
            days=self.review_period_days
        )
        entries: list = []

        for filename in sorted(os.listdir(logs_dir)):
            if not filename.endswith(".json"):
                continue
            filepath = os.path.join(logs_dir, filename)
            try:
                with open(filepath, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    if isinstance(data, list):
                        for entry in data:
                            ts = datetime.datetime.fromisoformat(
                                entry.get("timestamp", "")
                            )
                            if ts >= cutoff:
                                entries.append(entry)
                    elif isinstance(data, dict):
                        ts = datetime.datetime.fromisoformat(
                            data.get("timestamp", "")
                        )
                        if ts >= cutoff:
                            entries.append(data)
            except Exception as e:
                print(f"[{self.name}] Skipping log file {filename}: {e}")

        return entries

    # ------------------------------------------------------------------
    # Aggregate stats per agent
    # ------------------------------------------------------------------

    @staticmethod
    def _aggregate_stats(logs: list) -> dict:
        """Group log entries by agent_id and compute summary stats."""
        stats: dict = {}
        for entry in logs:
            aid = entry.get("agent_id", "unknown")
            if aid not in stats:
                stats[aid] = {
                    "runs": 0,
                    "successes": 0,
                    "errors": 0,
                    "total_steps": 0,
                    "total_duration": 0,
                    "max_steps_configured": 0,
                    "tasks_completed": []
                }
            s = stats[aid]
            s["runs"] += 1
            s["total_steps"] += entry.get("steps_used", 0)
            s["total_duration"] += entry.get("duration_seconds", 0)
            s["errors"] += len(entry.get("errors", []))
            s["max_steps_configured"] = max(
                s["max_steps_configured"], entry.get("max_steps", 0)
            )
            if entry.get("outcome") == "success":
                s["successes"] += 1
            task = entry.get("task_summary", "")
            if task:
                s["tasks_completed"].append(task)

        return stats

    # ------------------------------------------------------------------
    # Load declared success metrics from agent class
    # ------------------------------------------------------------------

    def _load_agent_success_metrics(self, module_path: str, class_name: str) -> dict:
        """Dynamically import an agent module and read its success_metrics."""
        try:
            mod = importlib.import_module(module_path)
            cls = getattr(mod, class_name)
            # Most agents expect an llm_client in their constructor
            instance = cls(self.llm_client)
            return getattr(instance, "success_metrics", {})
        except Exception as e:
            return {"_load_error": str(e)}

    # ------------------------------------------------------------------
    # Grading engine
    # ------------------------------------------------------------------

    def _grade_agent(self, agent_id: str, registry_entry: dict,
                     agent_stats: dict, declared_metrics: dict) -> dict:
        """Evaluate a single agent and assign a letter grade.

        Grading rubric:
          A  — All metrics met or exceeded, no errors, active usage
          B  — Metrics mostly met, error rate < 5%, active usage
          C  — Some metrics missed or error rate 5-15%
          D  — Multiple metrics missed, error rate 15-30%
          F  — No activity, critical metric failures, or error rate > 30%
        """
        agent_class = registry_entry.get("class", agent_id)
        review: dict = {
            "agent_id": agent_id,
            "agent_class": agent_class,
            "declared_metrics": declared_metrics,
            "findings": [],
            "grade": "A",
            "mandates": []
        }

        # --- No activity check ---
        if not agent_stats or agent_stats.get("runs", 0) == 0:
            review["grade"] = "F"
            review["findings"].append(
                "No interaction data recorded during the review period."
            )
            review["mandates"].append(
                "Ensure this agent is invoked at least once per week and "
                "emits structured logs to .exegol/interaction_logs/."
            )
            return review

        runs = agent_stats["runs"]
        successes = agent_stats["successes"]
        errors = agent_stats["errors"]
        total_steps = agent_stats["total_steps"]
        max_steps_cfg = registry_entry.get("max_steps", 0)

        success_rate = successes / runs if runs else 0
        error_rate = errors / runs if runs else 0
        avg_steps = total_steps / runs if runs else 0
        step_efficiency = (avg_steps / max_steps_cfg) if max_steps_cfg else 0

        review["computed_stats"] = {
            "runs": runs,
            "success_rate": f"{success_rate:.0%}",
            "error_rate": f"{error_rate:.0%}",
            "avg_steps": round(avg_steps, 1),
            "step_efficiency": f"{step_efficiency:.0%}",
            "tasks_completed": len(agent_stats.get("tasks_completed", []))
        }

        # --- Grading logic ---
        penalty_points = 0

        # Error rate assessment
        if error_rate > 0.30:
            penalty_points += 4
            review["findings"].append(
                f"Critical error rate: {error_rate:.0%}. "
                "More than 30% of runs encountered errors."
            )
            review["mandates"].append(
                "Conduct root-cause analysis on failures. Add input validation "
                "and retry logic. Target error rate <5%."
            )
        elif error_rate > 0.15:
            penalty_points += 3
            review["findings"].append(
                f"High error rate: {error_rate:.0%}."
            )
            review["mandates"].append(
                "Review error logs and add defensive checks. "
                "Target error rate <10%."
            )
        elif error_rate > 0.05:
            penalty_points += 1
            review["findings"].append(
                f"Moderate error rate: {error_rate:.0%}."
            )

        # Success rate assessment
        if success_rate < 0.50:
            penalty_points += 3
            review["findings"].append(
                f"Low success rate: {success_rate:.0%}."
            )
            review["mandates"].append(
                "Investigate why >50% of runs are not succeeding. "
                "Review prompts, tool availability, and input data."
            )
        elif success_rate < 0.80:
            penalty_points += 1
            review["findings"].append(
                f"Below-target success rate: {success_rate:.0%}."
            )

        # Step efficiency (using >80% of budget consistently is a concern)
        if step_efficiency > 0.90 and max_steps_cfg > 0:
            penalty_points += 1
            review["findings"].append(
                f"Step budget nearly exhausted: using {step_efficiency:.0%} "
                f"of {max_steps_cfg} allocated steps on average."
            )
            review["mandates"].append(
                "Consider increasing max_steps or optimising the agent's "
                "reasoning chain to reduce step consumption."
            )
        elif step_efficiency < 0.20 and max_steps_cfg > 5:
            review["findings"].append(
                f"Very low step utilisation ({step_efficiency:.0%}). "
                "Consider reducing max_steps to free budget."
            )

        # Low activity (< 2 runs in a week may indicate routing issues)
        if runs < 2:
            penalty_points += 1
            review["findings"].append(
                f"Only {runs} run(s) this week — low utilisation."
            )

        # Metrics assessment
        if not declared_metrics or "_load_error" in declared_metrics:
            error_msg = declared_metrics.get('_load_error', 'No success_metrics defined') if declared_metrics else 'No success_metrics defined'
            review["findings"].append(
                f"Could not load success_metrics: {error_msg}"
            )
            penalty_points += 1

        # No findings is excellent
        if not review["findings"]:
            review["findings"].append(
                "All indicators healthy. Agent operating within expectations."
            )

        # Map penalty points to letter grade
        if penalty_points == 0:
            review["grade"] = "A"
        elif penalty_points == 1:
            review["grade"] = "B"
        elif penalty_points <= 3:
            review["grade"] = "C"
        elif penalty_points <= 5:
            review["grade"] = "D"
        else:
            review["grade"] = "F"

        return review

    # ------------------------------------------------------------------
    # Email composition
    # ------------------------------------------------------------------

    def _compose_review_email(self, reviews: list,
                              fleet_summary: dict) -> dict:
        """Build an HTML email summarising all agent performance reviews."""

        now = datetime.datetime.now()
        week_start = (now - datetime.timedelta(days=7)).strftime("%b %d")
        week_end = now.strftime("%b %d, %Y")

        grade_colors = {
            "A": "#51cf66", "B": "#94d82d", "C": "#ffd43b",
            "D": "#ff922b", "F": "#ff6b6b"
        }

        # Grade distribution
        grade_counts = {}
        for r in reviews:
            g = r["grade"]
            grade_counts[g] = grade_counts.get(g, 0) + 1

        grade_dist_html = " | ".join(
            f"<span style='color:{grade_colors.get(g, '#fff')};font-weight:bold;'>"
            f"{g}: {c}</span>"
            for g, c in sorted(grade_counts.items())
        )

        # Per-agent review rows
        review_rows = ""
        for r in sorted(reviews, key=lambda x: x["grade"]):
            color = grade_colors.get(r["grade"], "#fff")
            findings_html = "<br>".join(f"• {f}" for f in r["findings"])
            mandates_html = ""
            if r["mandates"]:
                mandates_html = "<br>".join(
                    f"→ {m}" for m in r["mandates"]
                )
            else:
                mandates_html = "<em style='color:#666;'>None</em>"

            stats_html = ""
            if "computed_stats" in r:
                cs = r["computed_stats"]
                stats_html = (
                    f"Runs: {cs['runs']} | "
                    f"Success: {cs['success_rate']} | "
                    f"Errors: {cs['error_rate']} | "
                    f"Avg Steps: {cs['avg_steps']}"
                )

            review_rows += f"""\
<tr style="border-bottom:2px solid #333;">
  <td style="padding:10px 12px;vertical-align:top;">
    <span style="font-size:24px;font-weight:bold;color:{color};">{r['grade']}</span>
  </td>
  <td style="padding:10px 12px;vertical-align:top;">
    <strong>{r['agent_class']}</strong>
    <div style="font-size:12px;color:#888;margin-top:4px;">{stats_html}</div>
  </td>
  <td style="padding:10px 12px;vertical-align:top;font-size:13px;">
    {findings_html}
  </td>
  <td style="padding:10px 12px;vertical-align:top;font-size:13px;color:#ffd43b;">
    {mandates_html}
  </td>
</tr>"""

        # Underperformers callout
        underperformers = [r for r in reviews if r["grade"] in ("C", "D", "F")]
        if underperformers:
            underperformer_callout = f"""\
<div style="background:#3a1a1a;border-left:4px solid #ff6b6b;padding:12px;margin:16px 0;">
  <strong style="color:#ff6b6b;">⚠ {len(underperformers)} agent(s) require attention:</strong>
  <ul style="margin:8px 0;">
    {"".join(f"<li><strong>{u['agent_class']}</strong> — Grade {u['grade']}</li>" for u in underperformers)}
  </ul>
</div>"""
        else:
            underperformer_callout = """\
<div style="background:#1a3a1a;border-left:4px solid #51cf66;padding:12px;margin:16px 0;">
  <strong style="color:#51cf66;">✅ All agents performing at B or above.</strong>
</div>"""

        html_body = f"""\
<html>
<body style="font-family:Arial,sans-serif;background:#1a1a2e;color:#e0e0e0;padding:24px;">
<h2 style="color:#00d4ff;">👔 Chief of Staff — Agent Performance Review</h2>
<p style="color:#aaa;">Review Period: {week_start} – {week_end}</p>

<h3 style="color:#00d4ff;">📊 Grade Distribution</h3>
<p style="font-size:16px;">{grade_dist_html}</p>

{underperformer_callout}

<h3 style="color:#ffd43b;">📋 Individual Reviews</h3>
<table style="width:100%;border-collapse:collapse;">
<tr style="background:#2a2a4a;">
  <th style="padding:8px 12px;text-align:left;">Grade</th>
  <th style="padding:8px 12px;text-align:left;">Agent</th>
  <th style="padding:8px 12px;text-align:left;">Findings</th>
  <th style="padding:8px 12px;text-align:left;">Mandates</th>
</tr>
{review_rows}
</table>

<hr style="border-color:#333;margin-top:24px;">
<p style="color:#666;font-size:12px;">
  Sent by ChiefOfStaffChewieAgent · Exegol v3 Orchestrator
</p>
</body>
</html>"""

        return {
            "to": self.report_email,
            "subject": (
                f"👔 Agent Performance Review — "
                f"Week {now.isocalendar()[1]} ({week_start} – {week_end})"
            ),
            "body_html": html_body
        }

    # ------------------------------------------------------------------
    # Main execution
    # ------------------------------------------------------------------

    def run_monthly_review(self, handoff):
        """Execute a comprehensive monthly review of the agent fleet.
        
        Ensures all agents have success criteria, creates backlog tasks for improvements 
        (routed to Product Poe), requests clarifications via Thoughtful Thrawn (Slack), 
        and emails the report.
        """
        from agents.registry import AGENT_REGISTRY
        from tools.backlog_manager import BacklogManager
        from tools.slack_tool import post_to_slack

        repo_path = handoff.repo_path
        print(f"[{self.name}] Session {handoff.session_id} — monthly performance review starting.")

        # Temporarily set review period to 30 days for monthly review
        original_period = self.review_period_days
        self.review_period_days = 30

        logs = self._load_interaction_logs(repo_path)
        agent_stats = self._aggregate_stats(logs)
        
        bm = BacklogManager(repo_path)
        reviews = []
        improvements = []
        clarifications = []

        for agent_id, entry in AGENT_REGISTRY.items():
            if agent_id == "chief_of_staff_chewie":
                continue

            module_path = entry.get("module", "")
            class_name = entry.get("class", "")

            declared_metrics = self._load_agent_success_metrics(module_path, class_name)
            
            review = self._grade_agent(agent_id, entry, agent_stats.get(agent_id), declared_metrics)
            reviews.append(review)

            # Check for missing success criteria
            if not declared_metrics or "_load_error" in declared_metrics:
                task_id = f"improve_{agent_id}_metrics_{int(datetime.datetime.now().timestamp())}"
                task = {
                    "id": task_id,
                    "summary": f"Define and implement success criteria for {class_name}",
                    "priority": "high",
                    "type": "architecture_improvement",
                    "status": "todo",
                    "source_agent": self.name,
                    "rationale": "Monthly review identified missing success criteria. Routing to Product Poe for prioritization.",
                    "created_at": datetime.datetime.now().isoformat()
                }
                bm.add_task(task)
                improvements.append(task)
                clarifications.append(f"What should the success criteria be for {class_name}?")

            # If grade indicates underperformance, create optimization task
            if review["grade"] in ["C", "D", "F"]:
                task_id = f"optimize_{agent_id}_{int(datetime.datetime.now().timestamp())}"
                task = {
                    "id": task_id,
                    "summary": f"Optimize and improve {class_name} performance (Grade: {review['grade']})",
                    "priority": "high",
                    "type": "bug",
                    "status": "todo",
                    "source_agent": self.name,
                    "rationale": f"Monthly review flagged {class_name} with grade {review['grade']}. Findings: {'; '.join(review['findings'])}",
                    "created_at": datetime.datetime.now().isoformat()
                }
                bm.add_task(task)
                improvements.append(task)

        # Send clarifications to Thoughtful Thrawn to discuss with human
        if clarifications:
            msg = f"🤔 *Monthly Review Clarification Needed (Routing to Thoughtful Thrawn)*:\n"
            for c in clarifications:
                msg += f"• {c}\n"
            msg += "\n_Please provide answers to unblock agent optimizations._"
            post_to_slack(msg)

        # Fleet summary
        grade_dist = {}
        for r in reviews:
            g = r["grade"]
            grade_dist[g] = grade_dist.get(g, 0) + 1
        underperformers = [r for r in reviews if r["grade"] in ("C", "D", "F")]

        fleet_summary = {
            "total_reviewed": len(reviews),
            "grade_distribution": grade_dist,
            "underperformers": len(underperformers)
        }

        # Compose email
        email_payload = self._compose_review_email(reviews, fleet_summary)
        email_payload["subject"] = email_payload["subject"].replace("Week", "Month")
        
        # Save report
        exegol_dir = os.path.join(repo_path, ".exegol")
        reports_dir = os.path.join(exegol_dir, "performance_reviews")
        os.makedirs(reports_dir, exist_ok=True)
        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        report_file = os.path.join(reports_dir, f"monthly_review_{timestamp}.json")

        report_data = {
            "generated_at": timestamp,
            "review_period_days": self.review_period_days,
            "fleet_summary": fleet_summary,
            "reviews": reviews,
            "improvements_identified": len(improvements),
            "email_subject": email_payload["subject"],
            "email_to": email_payload["to"]
        }
        with open(report_file, "w", encoding="utf-8") as f:
            json.dump(report_data, f, indent=4, default=str)

        # 7. Send email via real gmail_api tool
        print(f"[{self.name}] Sending monthly review to {self.report_email}...")
        
        text_body = (
            f"Chief of Staff — Monthly Agent Performance Review\n"
            f"Total Reviewed: {fleet_summary['total_reviewed']}\n"
            f"Underperformers: {fleet_summary['underperformers']}\n"
            f"Improvements Identified: {len(improvements)}\n"
            f"Please view in an HTML-compatible email client for full details."
        )
        
        try:
            result = send_gmail_message(
                to=self.report_email,
                subject=email_payload["subject"],
                body=text_body,
                body_html=email_payload["body_html"]
            )
            print(f"[{self.name}] {result}")
        except Exception as e:
            error_msg = f"Gmail Send Failure: {str(e)}"
            print(f"[{self.name}] CRITICAL: {error_msg}")
            
            # 8. Self-Healing: Route own failure to Product Poe and Thoughtful Thrawn
            error_task = {
                "id": f"fix_gmail_integration_{int(datetime.datetime.now().timestamp())}",
                "summary": "Fix Gmail API Integration / Refresh OAuth Token",
                "priority": "critical",
                "type": "bug",
                "status": "todo",
                "source_agent": self.name,
                "rationale": f"Monthly review failed to send report via Gmail. Error: {error_msg}. Manual token refresh or dependency check required.",
                "created_at": datetime.datetime.now().isoformat()
            }
            bm.add_task(error_task)
            
            # Notify Thrawn/Slack about the block
            slack_msg = (
                f"🚨 *CRITICAL BLOCKER*: `{self.name}` failed to deliver the Monthly Review.\n"
                f"*Error*: `{error_msg}`\n"
                f"*Action Required*: Please run `python generate_token.py` or check dependencies to unblock fleet reporting."
            )
            post_to_slack(slack_msg)
            
            return (
                f"Monthly review generated but email delivery FAILED. "
                f"A critical task has been added to the backlog and Thrawn has been notified. "
                f"Report saved: {report_file}"
            )

        # Restore review period
        self.review_period_days = original_period

        return (
            f"Monthly performance review complete. {len(reviews)} agents reviewed. "
            f"Grades: {grade_dist}. {len(improvements)} improvement tasks added to backlog. "
            f"Report saved: {report_file}"
        )

    def execute(self, handoff):
        """Run the performance review cycle for all registered agents.

        Accepts a HandoffContext — no prior session memory required.
        All state is read fresh from the filesystem.
        """
        from agents.registry import AGENT_REGISTRY

        repo_path = handoff.repo_path
        print(f"[{self.name}] Session {handoff.session_id} — performance review cycle starting.")

        # 1. Load interaction logs
        logs = self._load_interaction_logs(repo_path)
        print(f"[{self.name}] Loaded {len(logs)} log entries "
              f"(last {self.review_period_days} days).")

        # 2. Aggregate per-agent stats
        agent_stats = self._aggregate_stats(logs)
        print(f"[{self.name}] Stats aggregated for "
              f"{len(agent_stats)} agents with activity.")

        # 3. Review each registered agent
        reviews = []
        for agent_id, entry in AGENT_REGISTRY.items():
            # Don't review yourself
            if agent_id == "chief_of_staff_chewie":
                continue

            module_path = entry.get("module", "")
            class_name = entry.get("class", "")

            # Load declared success metrics
            declared_metrics = self._load_agent_success_metrics(
                module_path, class_name
            )

            # Grade this agent
            stats_for_agent = agent_stats.get(agent_id)
            review = self._grade_agent(
                agent_id, entry, stats_for_agent, declared_metrics
            )
            reviews.append(review)

            grade_emoji = {"A": "🟢", "B": "🟡", "C": "🟠",
                           "D": "🔴", "F": "⛔"}.get(review["grade"], "❓")
            print(f"[{self.name}] {grade_emoji} {class_name}: "
                  f"Grade {review['grade']}")

        # 4. Fleet summary
        grade_dist = {}
        for r in reviews:
            g = r["grade"]
            grade_dist[g] = grade_dist.get(g, 0) + 1
        underperformers = [r for r in reviews if r["grade"] in ("C", "D", "F")]

        fleet_summary = {
            "total_reviewed": len(reviews),
            "grade_distribution": grade_dist,
            "underperformers": len(underperformers)
        }

        print(f"[{self.name}] Reviews complete: {len(reviews)} agents reviewed.")
        print(f"[{self.name}] Grade distribution: {grade_dist}")
        if underperformers:
            print(f"[{self.name}] ⚠ {len(underperformers)} underperformer(s) flagged.")

        # 5. Compose email
        email_payload = self._compose_review_email(reviews, fleet_summary)

        # 6. Persist review report
        exegol_dir = os.path.join(repo_path, ".exegol")
        os.makedirs(exegol_dir, exist_ok=True)
        reports_dir = os.path.join(exegol_dir, "performance_reviews")
        os.makedirs(reports_dir, exist_ok=True)

        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        report_file = os.path.join(reports_dir, f"review_{timestamp}.json")

        report_data = {
            "generated_at": timestamp,
            "review_period_days": self.review_period_days,
            "fleet_summary": fleet_summary,
            "reviews": reviews,
            "email_subject": email_payload["subject"],
            "email_to": email_payload["to"]
        }
        with open(report_file, "w", encoding="utf-8") as f:
            json.dump(report_data, f, indent=4, default=str)

        print(f"[{self.name}] Review report persisted to {report_file}")

        # 7. Send email via real gmail_api tool
        print(f"[{self.name}] Sending review to {self.report_email}...")
        
        # Create a simple plain-text fallback
        text_body = (
            f"Chief of Staff — Agent Performance Review\n"
            f"Total Reviewed: {fleet_summary['total_reviewed']}\n"
            f"Underperformers: {fleet_summary['underperformers']}\n"
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
            f"Performance review complete. {len(reviews)} agents reviewed. "
            f"Grades: {grade_dist}. "
            f"{len(underperformers)} underperformer(s) flagged. "
            f"Report saved: {report_file}"
        )
