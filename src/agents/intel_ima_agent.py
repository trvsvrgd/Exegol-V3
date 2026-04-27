import os
import json
import datetime
from tools.web_search import web_search


class IntelImaAgent:
    """Generates intelligence reports, cost analysis summaries, and delivers weekly email digests."""

    def __init__(self, llm_client):
        self.llm_client = llm_client
        self.name = "IntelImaAgent"
        self.max_steps = 5
        self.tools = ["gmail_api", "drive_sync", "cost_analyzer", "web_search"]
        self.success_metrics = {
            "weekly_reports_delivered": {
                "description": "Percentage of weeks with a report emailed on time",
                "target": "100%",
                "current": None
            },
            "cost_anomalies_flagged": {
                "description": "Number of cost spikes detected and reported vs total spikes",
                "target": "all",
                "current": None
            }
        }
        self.system_prompt = self.llm_client.generate_system_prompt(self)


    def execute(self, handoff):
        """Execute with a clean HandoffContext — no prior session memory required.

        Generates an intelligence report from filesystem data.
        """
        repo_path = handoff.repo_path
        print(f"[{self.name}] Session {handoff.session_id} — waking up for repo: {repo_path}")
        print(f"[{self.name}] Researching latest AI cost trends...")
        
        # Phase 2: Web Search Integration for Intelligence
        market_query = "latest LLM API pricing trends and open source inference cost 2024 2025"
        market_intel = web_search(market_query, num_results=3)
        
        print(f"[{self.name}] Generating intelligence report...")

        exegol_dir = os.path.join(repo_path, ".exegol")
        os.makedirs(exegol_dir, exist_ok=True)

        reports_dir = os.path.join(exegol_dir, "intel_reports")
        os.makedirs(reports_dir, exist_ok=True)

        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        report_file = os.path.join(reports_dir, f"weekly_{timestamp}.json")

        # Mock report generation — real implementation would pull from
        # gmail_api, drive_sync, and cost_analyzer tools.
        report = {
            "type": "weekly",
            "generated_at": timestamp,
            "session_id": handoff.session_id,
            "summary": "All systems nominal. No cost anomalies detected.",
            "market_intel_snippet": str(market_intel)[:200],
            "cost_breakdown": {},
            "recommendations": ["Consider transitioning to local vLLM for high-throughput tasks based on latest pricing trends."]
        }

        with open(report_file, 'w', encoding='utf-8') as f:
            json.dump(report, f, indent=4)

        print(f"[{self.name}] Report saved to {report_file}")
        return f"Intelligence report generated: {report_file}"
