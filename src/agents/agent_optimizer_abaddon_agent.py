import os
import json
import datetime
from tools.gmail_tool import send_gmail_message


class AgentOptimizerAbaddonAgent:
    """Reviews last week's agent interactions and proposes improvements,
    free tool recommendations, and paid tool recommendations via weekly email."""

    def __init__(self, llm_client):
        self.llm_client = llm_client
        self.name = "AgentOptimizerAbaddonAgent"
        self.max_steps = 10
        self.tools = ["gmail_api", "interaction_log_reader", "web_search"]
        self.report_email = "travisvreugdenhil@gmail.com"
        self.success_metrics = {
            "agents_with_suggestion": {
                "description": "Every registered agent has >= 1 improvement in every weekly email",
                "target": "100%",
                "current": None
            },
            "free_tool_recommended": {
                "description": "Exactly 1 free tool recommendation per weekly email",
                "target": "1",
                "current": None
            },
            "paid_tool_recommended": {
                "description": "Exactly 1 paid tool with business case per weekly email",
                "target": "1",
                "current": None
            },
            "emails_delivered_on_time": {
                "description": "Percentage of weeks with the optimization email delivered",
                "target": "100%",
                "current": None
            }
        }
        self.system_prompt = self.llm_client.generate_system_prompt(self)


    # ------------------------------------------------------------------
    # Interaction log helpers
    # ------------------------------------------------------------------

    def _load_interaction_logs(self, repo_path: str) -> list:
        """Load the last 7 days of agent interaction logs.

        Expected log schema per entry:
        {
            "agent_id": "developer_dragon",
            "timestamp": "2026-04-12T09:15:00",
            "steps_used": 8,
            "max_steps": 20,
            "errors": 0,
            "outcome": "success",
            "duration_seconds": 42
        }
        """
        logs_dir = os.path.join(repo_path, ".exegol", "interaction_logs")
        if not os.path.isdir(logs_dir):
            print(f"[{self.name}] No interaction_logs directory found at {logs_dir}. "
                  "Using synthetic data for initial run.")
            return []

        seven_days_ago = datetime.datetime.now() - datetime.timedelta(days=7)
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
                            ts = datetime.datetime.fromisoformat(entry.get("timestamp", ""))
                            if ts >= seven_days_ago:
                                entries.append(entry)
                    elif isinstance(data, dict):
                        ts = datetime.datetime.fromisoformat(data.get("timestamp", ""))
                        if ts >= seven_days_ago:
                            entries.append(data)
            except Exception as e:
                print(f"[{self.name}] Skipping log file {filename}: {e}")

        return entries

    # ------------------------------------------------------------------
    # Analysis engine
    # ------------------------------------------------------------------

    def _analyze_agents(self, logs: list, registry: dict) -> list:
        """Produce one suggested improvement per registered agent."""

        # Aggregate stats per agent
        stats: dict = {}
        for entry in logs:
            aid = entry.get("agent_id", "unknown")
            if aid not in stats:
                stats[aid] = {"runs": 0, "total_steps": 0, "errors": 0, "max_steps": 0}
            stats[aid]["runs"] += 1
            stats[aid]["total_steps"] += entry.get("steps_used", 0)
            stats[aid]["errors"] += len(entry.get("errors", []))
            stats[aid]["max_steps"] = max(stats[aid]["max_steps"],
                                          entry.get("max_steps", 0))

        suggestions = []
        for agent_id, details in registry.items():
            agent_class = details.get("class", agent_id)
            agent_stats = stats.get(agent_id)

            if agent_stats and agent_stats["runs"] > 0:
                avg_steps = agent_stats["total_steps"] / agent_stats["runs"]
                configured_max = details.get("max_steps", 0)
                error_rate = agent_stats["errors"] / agent_stats["runs"]

                if avg_steps < configured_max * 0.5:
                    suggestions.append({
                        "agent": agent_class,
                        "suggestion": (
                            f"Reduce max_steps from {configured_max} to "
                            f"{int(avg_steps * 1.5)} — average usage is only "
                            f"{avg_steps:.1f} steps, freeing budget for other agents."
                        )
                    })
                elif error_rate > 0.2:
                    suggestions.append({
                        "agent": agent_class,
                        "suggestion": (
                            f"Error rate is {error_rate:.0%}. Add retry logic or "
                            "pre-validation step to reduce failures."
                        )
                    })
                else:
                    suggestions.append({
                        "agent": agent_class,
                        "suggestion": (
                            "Performance is nominal. Consider adding structured "
                            "output logging to enable deeper future analysis."
                        )
                    })
            else:
                # No log data for this agent — provide a bootstrap suggestion
                suggestions.append({
                    "agent": agent_class,
                    "suggestion": (
                        "No interaction data recorded last week. "
                        "Ensure this agent emits logs to "
                        ".exegol/interaction_logs/ so optimizations can be tracked."
                    )
                })

        return suggestions

    # ------------------------------------------------------------------
    # Tool recommendations
    # ------------------------------------------------------------------

    @staticmethod
    def _recommend_free_tool() -> dict:
        """Return a single free tool recommendation.

        In a production implementation this would query web_search for the
        latest trending developer tools and cross-reference with the
        current toolset.  For now we maintain a curated rotation list.
        """
        # Rotation list — a real implementation would dynamically research.
        free_tools = [
            {
                "name": "LangSmith (free tier)",
                "url": "https://smith.langchain.com",
                "fit": (
                    "LangSmith provides tracing and observability for LLM-powered "
                    "agents at no cost on the free tier. It slots directly into "
                    "Exegol's orchestrator to visualize step-by-step agent "
                    "execution and pinpoint latency bottlenecks."
                )
            },
            {
                "name": "Ollama Web UI (Open WebUI)",
                "url": "https://github.com/open-webui/open-webui",
                "fit": (
                    "Open WebUI gives a ChatGPT-style frontend for local Ollama "
                    "models. It lets you manually test prompts destined for agents "
                    "before committing them, reducing iteration cycles."
                )
            },
            {
                "name": "Dagger.io",
                "url": "https://dagger.io",
                "fit": (
                    "Dagger lets you define CI/CD pipelines as code in Python. "
                    "It can replace ad-hoc shell scripts for daily commits and "
                    "PR creation, giving each agent a reproducible deploy path."
                )
            }
        ]
        week_number = datetime.datetime.now().isocalendar()[1]
        return free_tools[week_number % len(free_tools)]

    @staticmethod
    def _recommend_paid_tool() -> dict:
        """Return a single paid tool recommendation with business case."""
        paid_tools = [
            {
                "name": "Braintrust",
                "price_tier": "Team — $150/mo",
                "business_case": (
                    "Braintrust provides production-grade LLM eval and logging "
                    "with dataset versioning. For a 20-repo fleet generating "
                    "hundreds of agent runs per week, manual log inspection "
                    "doesn't scale. Braintrust would cut eval-cycle time by ~60% "
                    "and surface regressions automatically before they reach "
                    "production."
                )
            },
            {
                "name": "Linear",
                "price_tier": "Standard — $8/user/mo",
                "business_case": (
                    "Linear replaces the flat backlog.json files with a real "
                    "project tracker that supports priorities, sprints, and "
                    "agent-generated tickets via API. At $8/mo for a single seat "
                    "it would eliminate manual grooming overhead and give "
                    "ProductivePuckAgent a structured API to write to."
                )
            },
            {
                "name": "Weights & Biases (W&B)",
                "price_tier": "Teams — $50/seat/mo",
                "business_case": (
                    "W&B provides experiment tracking and model performance "
                    "dashboards. With ResourcefulRavenAgent constantly evaluating "
                    "new models, W&B would provide side-by-side comparison charts "
                    "and automated performance reports, making model upgrade "
                    "decisions data-driven instead of gut-feel."
                )
            }
        ]
        week_number = datetime.datetime.now().isocalendar()[1]
        return paid_tools[week_number % len(paid_tools)]

    # ------------------------------------------------------------------
    # Email composition
    # ------------------------------------------------------------------

    def _compose_email(self, suggestions: list, free_tool: dict,
                       paid_tool: dict) -> dict:
        """Build the email payload."""

        # Build per-agent HTML rows
        agent_rows = "\n".join(
            f"<tr><td style='padding:6px 12px;border-bottom:1px solid #333'>"
            f"<strong>{s['agent']}</strong></td>"
            f"<td style='padding:6px 12px;border-bottom:1px solid #333'>"
            f"{s['suggestion']}</td></tr>"
            for s in suggestions
        )

        html_body = f"""\
<html>
<body style="font-family:Arial,sans-serif;background:#1a1a2e;color:#e0e0e0;padding:24px;">
<h2 style="color:#00d4ff;">⚡ Exegol Weekly Agent Optimization Report</h2>
<p style="color:#aaa;">Generated {datetime.datetime.now().strftime('%Y-%m-%d %H:%M')}</p>

<h3 style="color:#ff6b6b;">🔧 Per-Agent Improvements</h3>
<table style="width:100%;border-collapse:collapse;">
<tr style="background:#2a2a4a;">
  <th style="padding:8px 12px;text-align:left;">Agent</th>
  <th style="padding:8px 12px;text-align:left;">Suggested Improvement</th>
</tr>
{agent_rows}
</table>

<h3 style="color:#51cf66;">🆓 Free Tool Recommendation</h3>
<p><strong>{free_tool['name']}</strong>
   — <a href="{free_tool['url']}" style="color:#00d4ff;">{free_tool['url']}</a></p>
<p>{free_tool['fit']}</p>

<h3 style="color:#ffd43b;">💰 Paid Tool Recommendation</h3>
<p><strong>{paid_tool['name']}</strong> ({paid_tool['price_tier']})</p>
<p>{paid_tool['business_case']}</p>

<hr style="border-color:#333;">
<p style="color:#666;font-size:12px;">
  Sent by AbaddonAgentOptimizerAgent · Exegol v3 Orchestrator
</p>
</body>
</html>"""

        return {
            "to": self.report_email,
            "subject": (
                f"⚡ Exegol Agent Optimization — "
                f"Week {datetime.datetime.now().isocalendar()[1]}"
            ),
            "body_html": html_body
        }

    # ------------------------------------------------------------------
    # Validation
    # ------------------------------------------------------------------

    def _validate_output(self, suggestions: list, free_tool: dict,
                         paid_tool: dict, registry: dict) -> bool:
        """Ensure the output meets all success criteria before sending."""
        agents_covered = {s["agent"] for s in suggestions}
        registry_classes = {v["class"] for v in registry.values()}

        if not registry_classes.issubset(agents_covered):
            missing = registry_classes - agents_covered
            print(f"[{self.name}] VALIDATION FAIL — missing suggestions for: {missing}")
            return False

        if not free_tool or "name" not in free_tool:
            print(f"[{self.name}] VALIDATION FAIL — no free tool recommendation.")
            return False

        if not paid_tool or "business_case" not in paid_tool:
            print(f"[{self.name}] VALIDATION FAIL — no paid tool business case.")
            return False

        print(f"[{self.name}] Validation passed.")
        return True

    # ------------------------------------------------------------------
    # Main execution
    # ------------------------------------------------------------------

    def execute(self, handoff):
        """Run the weekly optimization cycle.

        Accepts a HandoffContext — no prior session memory required.
        All state is read fresh from the filesystem.
        """
        from agents.registry import AGENT_REGISTRY

        repo_path = handoff.repo_path
        print(f"[{self.name}] Session {handoff.session_id} — weekly optimization cycle starting.")

        # 1. Load interaction logs
        logs = self._load_interaction_logs(repo_path)
        print(f"[{self.name}] Loaded {len(logs)} interaction log entries from last 7 days.")

        # 2. Analyze each agent
        suggestions = self._analyze_agents(logs, AGENT_REGISTRY)
        print(f"[{self.name}] Generated {len(suggestions)} agent improvement suggestions.")

        # 3. Tool recommendations
        free_tool = self._recommend_free_tool()
        paid_tool = self._recommend_paid_tool()
        print(f"[{self.name}] Free tool: {free_tool['name']}  |  Paid tool: {paid_tool['name']}")

        # 4. Validate
        if not self._validate_output(suggestions, free_tool, paid_tool, AGENT_REGISTRY):
            return "Optimization report failed validation. No email sent."

        # 5. Compose email
        email_payload = self._compose_email(suggestions, free_tool, paid_tool)

        # 6. Persist report
        exegol_dir = os.path.join(repo_path, ".exegol")
        os.makedirs(exegol_dir, exist_ok=True)
        reports_dir = os.path.join(exegol_dir, "optimizer_reports")
        os.makedirs(reports_dir, exist_ok=True)

        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        report_file = os.path.join(reports_dir, f"weekly_{timestamp}.json")

        report_data = {
            "generated_at": timestamp,
            "suggestions": suggestions,
            "free_tool": free_tool,
            "paid_tool": paid_tool,
            "email_subject": email_payload["subject"],
            "email_to": email_payload["to"]
        }
        with open(report_file, "w", encoding="utf-8") as f:
            json.dump(report_data, f, indent=4)

        print(f"[{self.name}] Report persisted to {report_file}")

        # 7. Send email via real gmail_api tool
        print(f"[{self.name}] Sending email to {self.report_email}...")
        
        # Create a simple plain-text fallback
        text_body = (
            f"Exegol Weekly Agent Optimization Report\n"
            f"Agents Analyzed: {len(suggestions)}\n"
            f"Free Tool: {free_tool['name']}\n"
            f"Paid Tool: {paid_tool['name']}\n"
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
            f"Weekly optimization report generated and emailed. "
            f"{len(suggestions)} agent suggestions, "
            f"free tool: {free_tool['name']}, "
            f"paid tool: {paid_tool['name']}. "
            f"Report saved: {report_file}"
        )
