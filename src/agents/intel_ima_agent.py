import os
import json
import datetime
from tools.web_search import web_search
from tools.cost_analyzer import get_cost_report


class IntelImaAgent:
    """Generates intelligence reports, cost analysis summaries, and delivers weekly email digests.
    
    Phase 3 (arch_finops_dashboard): cost_breakdown is now powered by the real
    CostAnalyzer tool, which reads fleet interaction logs to compute per-agent
    token consumption and spend estimates.
    """

    def __init__(self, llm_client):
        self.llm_client = llm_client
        self.name = "IntelImaAgent"
        self.max_steps = 5
        self.tools = ["cost_analyzer", "web_search", "gmail_api", "drive_sync"]
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

        Generates an intelligence report from real filesystem data via CostAnalyzer.
        """
        repo_path = handoff.repo_path
        print(f"[{self.name}] Session {handoff.session_id} — waking up for repo: {repo_path}")
        print(f"[{self.name}] Researching latest AI cost trends...")
        
        # Phase 2: Web Search Integration for Intelligence
        market_query = "latest LLM API pricing trends and open source inference cost 2024 2025"
        market_intel = web_search(market_query, num_results=3)
        
        # Phase 3: Real cost analysis via CostAnalyzer (arch_finops_dashboard)
        print(f"[{self.name}] Running real cost analysis via CostAnalyzer...")
        try:
            cost_report = get_cost_report(repo_path, days=30)
            cost_breakdown = cost_report.get("agent_costs", {})
            provider_breakdown = cost_report.get("provider_breakdown", {})
            total_spend = cost_report.get("total_spend", 0.0)
            cloud_status = cost_report.get("cloud_status", "Healthy")
            remaining_quota = cost_report.get("remaining_quota", 0.0)
            print(f"[{self.name}] Cost analysis complete. Total spend: ${total_spend:.4f}")
        except Exception as e:
            print(f"[{self.name}] CostAnalyzer warning: {e}. Using empty breakdown.")
            cost_breakdown = {}
            provider_breakdown = {}
            total_spend = 0.0
            cloud_status = "Unknown"
            remaining_quota = 0.0

        print(f"[{self.name}] Generating intelligence report...")

        exegol_dir = os.path.join(repo_path, ".exegol")
        os.makedirs(exegol_dir, exist_ok=True)

        reports_dir = os.path.join(exegol_dir, "intel_reports")
        os.makedirs(reports_dir, exist_ok=True)

        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        report_file = os.path.join(reports_dir, f"weekly_{timestamp}.json")

        # Real report — cost data sourced from CostAnalyzer (not mocked)
        report = {
            "type": "weekly",
            "generated_at": timestamp,
            "session_id": handoff.session_id,
            "summary": (
                f"Fleet nominal. Total spend: ${total_spend:.4f}. "
                f"Status: {cloud_status}. Remaining quota: ${remaining_quota:.2f}."
            ),
            "market_intel_snippet": str(market_intel)[:200],
            "cost_breakdown": cost_breakdown,
            "provider_breakdown": provider_breakdown,
            "total_spend": total_spend,
            "cloud_status": cloud_status,
            "remaining_quota": remaining_quota,
            "recommendations": self._generate_recommendations(
                total_spend, cloud_status, cost_breakdown
            )
        }

        with open(report_file, 'w', encoding='utf-8') as f:
            json.dump(report, f, indent=4)

        print(f"[{self.name}] Report saved to {report_file}")
        return f"Intelligence report generated: {report_file}. Spend: ${total_spend:.4f}. Status: {cloud_status}."

    def _generate_recommendations(self, total_spend: float, cloud_status: str, agent_costs: dict) -> list:
        """Generates cost recommendations based on real spend data."""
        recs = []

        if cloud_status == "Over Budget":
            recs.append("🚨 CRITICAL: Budget exceeded. Review agent scheduling and reduce high-frequency runs immediately.")
        elif cloud_status == "Near Limit":
            recs.append("⚠️ Budget near limit (>75% consumed). Consider switching high-cost agents to local Ollama models.")

        if total_spend == 0.0:
            recs.append("No billable sessions detected. Agents may be running on local models — cost efficiency is optimal.")
            return recs

        # Flag the top spending agent
        if agent_costs:
            top_agent = max(agent_costs, key=agent_costs.get)
            top_cost = agent_costs[top_agent]
            if top_cost > 0:
                recs.append(
                    f"Top spend agent: {top_agent} (${top_cost:.4f}). "
                    "Consider routing repetitive tasks to a lighter local model."
                )

        recs.append(
            "Consider transitioning high-throughput tasks to local vLLM for cost reduction "
            "based on current pricing trends."
        )
        return recs
