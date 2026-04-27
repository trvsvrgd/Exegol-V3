import os
import json
import datetime
from tools.gmail_tool import send_gmail_message


class OptimizerAhsokaAgent:
    """Reviews last week's agent interactions and proposes improvements,
    free tool recommendations, and paid tool recommendations via weekly email."""

    def __init__(self, llm_client):
        self.llm_client = llm_client
        self.name = "OptimizerAhsokaAgent"
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

    def _load_interaction_logs(self, repo_path: str, days: int = 7) -> list:
        """Load agent interaction logs for the specified number of days.
        If days is 0, load all history.

        Expected log schema per entry:
        {
            "agent_id": "developer_dex",
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

        cutoff = None
        if days > 0:
            cutoff = datetime.datetime.now() - datetime.timedelta(days=days)

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
                            if not cutoff or ts >= cutoff:
                                entries.append(entry)
                    elif isinstance(data, dict):
                        ts = datetime.datetime.fromisoformat(data.get("timestamp", ""))
                        if not cutoff or ts >= cutoff:
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
    # Milestone analysis (20x runs)
    # ------------------------------------------------------------------

    def _check_milestones(self, repo_path: str, all_logs: list, registry: dict):
        """Check if any agents have reached usage milestones and trigger analysis."""
        
        # Aggregate total runs per agent
        total_runs = {}
        for entry in all_logs:
            aid = entry.get("agent_id")
            if aid:
                total_runs[aid] = total_runs.get(aid, 0) + 1

        tracker_file = os.path.join(repo_path, ".exegol", "milestone_tracker.json")
        tracker = {}
        if os.path.exists(tracker_file):
            try:
                with open(tracker_file, "r") as f:
                    tracker = json.load(f)
            except:
                pass

        for agent_id, runs in total_runs.items():
            if runs >= 20:
                agent_tracker = tracker.get(agent_id, {"milestones": []})
                if "20_runs" not in agent_tracker["milestones"]:
                    print(f"[{self.name}] Agent {agent_id} reached 20 runs! Triggering deep analysis...")
                    
                    # 1. Perform deep analysis
                    agent_logs = [l for l in all_logs if l.get("agent_id") == agent_id]
                    backlog_items = self._analyze_agent_deep(agent_id, agent_logs, registry, repo_path)
                    
                    # 2. Append to backlog
                    if backlog_items:
                        self._append_to_backlog(repo_path, backlog_items)
                        print(f"[{self.name}] Added {len(backlog_items)} improvements for {agent_id} to backlog.")
                    
                    # 3. Update tracker
                    agent_tracker["milestones"].append("20_runs")
                    tracker[agent_id] = agent_tracker

        with open(tracker_file, "w") as f:
            json.dump(tracker, f, indent=4)

    def _analyze_agent_deep(self, agent_id: str, agent_logs: list, registry: dict, repo_path: str) -> list:
        """Use LLM to perform deep analysis of an agent after 20 runs."""
        details = registry.get(agent_id, {})
        agent_class = details.get("class", agent_id)
        
        # 1. Read agent source code
        source_code = "Source code not found."
        module_parts = details.get("module", "").split(".")
        if len(module_parts) >= 2:
            source_path = os.path.join(repo_path, "src", *module_parts) + ".py"
            if os.path.exists(source_path):
                with open(source_path, "r", encoding="utf-8") as f:
                    source_code = f.read()

        # 2. Prepare log summary
        log_summary = []
        for l in agent_logs[-10:]: # Look at last 10 logs for context
            summary = l.get("output_summary") or ""
            log_summary.append({
                "outcome": l.get("outcome"),
                "steps": l.get("steps_used"),
                "errors": l.get("errors"),
                "summary": summary[:200]
            })

        prompt = f"""
Analyze the following autonomous agent '{agent_class}' which has completed 20 runs.
Identify potential items for the product backlog to improve its performance, reliability, or capabilities.

AGENT SOURCE CODE:
```python
{source_code}
```

RECENT INTERACTION LOGS:
{json.dumps(log_summary, indent=2)}

Return a list of 2-3 specific, actionable backlog items in JSON format.
Each item must have: "id" (unique string), "summary" (short text), "priority" (high/medium/low), and "status" (todo).
Return ONLY the JSON array.
"""
        response = self.llm_client.generate(prompt, system_instruction="You are a system architect and performance optimizer.")
        items = self.llm_client.parse_json_response(response)
        
        if isinstance(items, list):
            # Ensure items are valid
            valid_items = []
            for item in items:
                if isinstance(item, dict) and "summary" in item:
                    item["id"] = item.get("id", f"opt_{agent_id}_{datetime.datetime.now().strftime('%f')}")
                    item["priority"] = item.get("priority", "medium")
                    item["status"] = "todo"
                    valid_items.append(item)
            return valid_items
        return []

    def _append_to_backlog(self, repo_path: str, new_items: list):
        """Append items to .exegol/backlog.json."""
        backlog_file = os.path.join(repo_path, ".exegol", "backlog.json")
        backlog = []
        if os.path.exists(backlog_file):
            try:
                with open(backlog_file, "r") as f:
                    backlog = json.load(f)
            except:
                pass
        
        backlog.extend(new_items)
        
        with open(backlog_file, "w") as f:
            json.dump(backlog, f, indent=4)

    # ------------------------------------------------------------------

    def _recommend_free_tool(self) -> dict:
        """Return a single free tool recommendation based on current trends.
        
        Dynamically researches latest trending developer tools via web_search.
        """
        print(f"[{self.name}] Searching for latest trending free developer tools...")
        from tools.web_search import web_search
        search_query = "latest trending free developer tools for AI agents 2024 2025"
        search_results = web_search(search_query, num_results=5)

        analysis_prompt = f"""
        Research Task: Recommend exactly one free developer tool for an AI agent fleet.
        Search Results: {json.dumps(search_results)}
        
        Return a JSON object with:
        - 'name': Name of the tool
        - 'url': Home page URL
        - 'fit': A 2-3 sentence explanation of how it fits the Exegol fleet.
        """
        
        response = self.llm_client.generate(analysis_prompt, system_instruction=self.system_prompt, json_format=True)
        tool = self.llm_client.parse_json_response(response)
        
        if not tool or not isinstance(tool, dict):
            # Fallback
            return {
                "name": "LangSmith (free tier)",
                "url": "https://smith.langchain.com",
                "fit": "LangSmith provides tracing and observability for LLM-powered agents at no cost on the free tier."
            }
        return tool


    def _recommend_paid_tool(self) -> dict:
        """Return a single paid tool recommendation with business case.
        
        Dynamically researches enterprise-grade AI tools via web_search.
        """
        print(f"[{self.name}] Searching for latest enterprise-grade AI tools...")
        from tools.web_search import web_search
        search_query = "latest enterprise AI agent observability and evaluation tools 2024 2025"
        search_results = web_search(search_query, num_results=5)

        analysis_prompt = f"""
        Research Task: Recommend exactly one paid developer tool for an AI agent fleet.
        Search Results: {json.dumps(search_results)}
        
        Return a JSON object with:
        - 'name': Name of the tool
        - 'price_tier': Estimated price (e.g. '$100/mo')
        - 'business_case': A 2-3 sentence business case for the Exegol fleet.
        """
        
        response = self.llm_client.generate(analysis_prompt, system_instruction=self.system_prompt, json_format=True)
        tool = self.llm_client.parse_json_response(response)
        
        if not tool or not isinstance(tool, dict):
            # Fallback
            return {
                "name": "Braintrust",
                "price_tier": "Team — $150/mo",
                "business_case": "Braintrust provides production-grade LLM eval and logging with dataset versioning."
            }
        return tool

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
  Sent by AhsokaAgent · Exegol v3 Orchestrator
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

        # 8. Check for usage milestones (e.g. 20 runs) and perform deep analysis
        all_logs = self._load_interaction_logs(repo_path, days=0)
        self._check_milestones(repo_path, all_logs, AGENT_REGISTRY)

        return (
            f"Weekly optimization report generated and emailed. "
            f"{len(suggestions)} agent suggestions, "
            f"free tool: {free_tool['name']}, "
            f"paid tool: {paid_tool['name']}. "
            f"Report saved: {report_file}"
        )
