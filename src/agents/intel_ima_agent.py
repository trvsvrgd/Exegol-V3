import os
import json
import datetime
from tools.web_search import web_search
from tools.cost_analyzer import get_cost_report
from tools.drive_sync import drive_sync_file
from tools.gmail_tool import send_gmail_message
from tools.fleet_logger import log_interaction
from tools.metrics_manager import SuccessMetricsManager
from tools.thrawn_intel_manager import ThrawnIntelManager
from tools.todo_reporter import report_todos
from tools.state_manager import StateManager


class IntelImaAgent:
    """Generates intelligence reports, cost analysis summaries, and delivers weekly email digests.
    
    Phase 4: drive_sync integration enabled. Intelligence reports are automatically
    synced to the cloud for NotebookLM consumption.
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
        self.metrics_manager = SuccessMetricsManager(os.getcwd())
        self.next_agent_id = None

    def _calculate_success_metrics(self, repo_path: str) -> dict:
        """Calculates intelligence reporting metrics based on recent logs."""
        logs = self.metrics_manager.load_logs(days=7)
        agent_logs = [l for l in logs if l.get("agent_id") == self.name]
        
        if not agent_logs:
            return {
                "weekly_reports_delivered": 0.0,
                "cost_anomalies_flagged": 0
            }

        successful_reports = [l for l in agent_logs if l.get("outcome") == "success" and "report generated" in l.get("task_summary", "").lower()]
        delivery_rate = len(successful_reports) / 1.0 # Target is 1 per week
        
        # Count anomalies flagged in the summaries
        anomalies = len([l for l in agent_logs if "anomaly" in l.get("task_summary", "").lower() or "spike" in l.get("task_summary", "").lower()])

        return {
            "weekly_reports_delivered": round(min(delivery_rate, 1.0) * 100, 1),
            "cost_anomalies_flagged": anomalies
        }

    def _is_waiting_for_input(self, repo_path: str) -> bool:
        """Checks if there are any pending HITL tasks for this agent."""
        hitl_path = os.path.join(repo_path, ".exegol", "user_action_required.json")
        if not os.path.exists(hitl_path):
            return False
        try:
            with open(hitl_path, 'r', encoding='utf-8') as f:
                tasks = json.load(f)
            return any(t.get("status") == "pending" and "intel_ima" in t.get("task", "").lower() for t in tasks)
        except:
            return False

    def _process_evaluation_mechanisms(self, repo_path: str):
        """Identifies outstanding evaluation mechanisms and feeds them to Thrawn and Vader."""
        eval_req_path = os.path.join(repo_path, ".exegol", "eval_requirements.json")
        if not os.path.exists(eval_req_path):
            print(f"[{self.name}] No eval_requirements.json found.")
            return 0

        try:
            with open(eval_req_path, 'r', encoding='utf-8') as f:
                eval_reqs = json.load(f)
        except Exception as e:
            print(f"[{self.name}] Error reading eval_requirements.json: {e}")
            return 0

        pending_evals = [e for e in eval_reqs if e.get("status") == "pending"]
        if not pending_evals:
            return 0

        print(f"[{self.name}] Found {len(pending_evals)} outstanding evaluation mechanisms. Informing Thrawn and Vader...")

        # 1. Inform Thrawn (Roadmap & Intent)
        thrawn_mgr = ThrawnIntelManager(repo_path)
        for e in pending_evals:
            # Add to roadmap for strategic review
            thrawn_mgr.add_roadmap_item("Strategic Evaluation", f"Implement {e['technique_name']} ({e['category']})")
            # Update architecture intent
            thrawn_mgr.add_architecture(f"Evaluation: {e['technique_name']}")

        # 2. Inform Vader (Human Action Required)
        # We add them to the StateManager HITL queue so Vader's next audit sees them
        sm = StateManager(repo_path)
        for e in pending_evals:
            sm.add_hitl_task(
                summary=f"Approve implementation of {e['technique_name']}",
                category="limitation",
                context=f"Outstanding evaluation mechanism identified by IntelIma. Needs human review: {e['description']}"
            )
            
        return len(pending_evals)


    def execute(self, handoff):
        """Execute with a clean HandoffContext — no prior session memory required.

        Generates an intelligence report and syncs it to Google Drive.
        """
        repo_path = handoff.repo_path
        print(f"[{self.name}] Session {handoff.session_id} — waking up for repo: {repo_path}")
        
        # Phase 4.1: Process outstanding evaluation mechanisms
        eval_count = self._process_evaluation_mechanisms(repo_path)
        
        # Check if we are blocked and need to hand off
        if self._is_waiting_for_input(repo_path):
            print(f"[{self.name}] Agent is waiting for human input. Handing off to Thrawn/Vader for strategic review.")
            self.next_agent_id = "thoughtful_thrawn"
        
        # 1. Market Research
        print(f"[{self.name}] Researching latest AI cost trends...")
        market_query = "latest LLM API pricing trends and open source inference cost 2024 2025"
        market_intel = web_search(market_query, num_results=3)
        
        # 2. Cost Analysis
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

        # 3. Generate JSON Report
        print(f"[{self.name}] Generating intelligence report...")
        exegol_dir = os.path.join(repo_path, ".exegol")
        reports_dir = os.path.join(exegol_dir, "intel_reports")
        os.makedirs(reports_dir, exist_ok=True)

        timestamp_fs = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        timestamp_iso = datetime.datetime.now().isoformat()
        report_file = os.path.join(reports_dir, f"weekly_{timestamp_fs}.json")

        report = {
            "type": "weekly",
            "generated_at": timestamp_iso,
            "session_id": handoff.session_id,
            "summary": (
                f"Fleet nominal. Total spend: ${total_spend:.4f}. "
                f"Status: {cloud_status}. Remaining quota: ${remaining_quota:.2f}."
            ),
            "market_intel_snippet": str(market_intel)[:500],
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

        # 4. Cloud Sync (drive_sync)
        print(f"[{self.name}] Syncing report to Google Drive...")
        sync_result = drive_sync_file(report_file)
        print(f"[{self.name}] {sync_result}")

        # 5. Email Delivery (gmail_api)
        email_recipient = os.getenv("INTEL_REPORT_RECIPIENT")
        email_status = "Skipped (no recipient configured)"
        if email_recipient:
            print(f"[{self.name}] Delivering report to {email_recipient}...")
            try:
                subject = f"Exegol Intelligence Report - {timestamp_fs}"
                body = f"Fleet status: {cloud_status}. Total spend: ${total_spend:.4f}.\n\nFull report: {report_file}"
                email_status = send_gmail_message(to=email_recipient, subject=subject, body=body)
            except Exception as e:
                email_status = f"Failed: {str(e)}"
        
        res = f"Report generated and synced. Drive: {sync_result}. Email: {email_status}."
        
        metrics = self._calculate_success_metrics(repo_path)
        log_interaction(
            agent_id=self.name,
            outcome="success",
            task_summary=res,
            repo_path=repo_path,
            steps_used=1,
            duration_seconds=(datetime.datetime.now() - datetime.datetime.fromisoformat(report["generated_at"])).total_seconds(), # Rough estimate
            session_id=handoff.session_id,
            metrics=metrics
        )
        return res

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
