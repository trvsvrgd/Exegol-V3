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
        """Calculates intelligence reporting metrics based on real fleet data."""
        # Use the specialized metrics manager for real data
        report = self.metrics_manager.calculate_metrics(days=7)
        agent_stats = report.get("agent_breakdown", {}).get(self.name, {})
        
        # Calculate delivery rate
        total_sessions = agent_stats.get("total_sessions", 0)
        success_rate = agent_stats.get("success_rate", 0.0)
        
        # Target is 1 successful report per week. 
        # If we have at least one successful session, we consider it 100% for the week.
        delivery_rate = 100.0 if success_rate > 0 and total_sessions > 0 else 0.0
        
        # Count anomalies flagged in the summaries by scanning logs
        logs = self.metrics_manager.load_logs(days=7)
        agent_logs = [l for l in logs if l.get("agent_id") == self.name]
        anomalies = len([l for l in agent_logs if "anomaly" in l.get("task_summary", "").lower() or "spike" in l.get("task_summary", "").lower()])

        return {
            "weekly_reports_delivered": delivery_rate,
            "cost_anomalies_flagged": anomalies,
            "fleet_recall": report.get("fleet_aggregate", {}).get("avg_recall", 0.0),
            "fleet_precision": report.get("fleet_aggregate", {}).get("avg_precision", 0.0)
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

        # 3. Collect Fleet Health Metrics
        print(f"[{self.name}] Gathering fleet health metrics...")
        metrics = self._calculate_success_metrics(repo_path)
        
        # 4. Collect Pending Strategic Debt (HITL Tasks)
        print(f"[{self.name}] Auditing pending strategic debt...")
        sm = StateManager(repo_path)
        hitl_tasks = sm.read_json(".exegol/user_action_required.json") or []
        pending_debt = [t for t in hitl_tasks if t.get("status") == "pending"]

        # 5. Generate Real Intelligence Analysis via LLM
        print(f"[{self.name}] Synthesizing intelligence report via LLM...")
        analysis = self._generate_intelligence_analysis(
            market_intel=market_intel,
            cost_report=cost_report,
            metrics=metrics,
            pending_debt=pending_debt
        )

        # 6. Save JSON Report
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
            "summary": analysis.get("executive_summary", "Fleet analysis complete."),
            "market_intel_snippet": str(market_intel)[:500],
            "cost_breakdown": cost_breakdown,
            "provider_breakdown": provider_breakdown,
            "total_spend": total_spend,
            "cloud_status": cloud_status,
            "remaining_quota": remaining_quota,
            "fleet_metrics": metrics,
            "recommendations": analysis.get("recommendations", []),
            "strategic_debt_count": len(pending_debt)
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
                
                # Generate pretty HTML body
                body_html = self._generate_html_report(report)
                
                # Plain text fallback
                body_text = (
                    f"Exegol Intelligence Report - {timestamp_fs}\n"
                    f"==========================================\n\n"
                    f"Fleet Status: {cloud_status}\n"
                    f"Total Spend: ${total_spend:.4f}\n"
                    f"Remaining Quota: ${remaining_quota:.2f}\n\n"
                    f"Summary: {report['summary']}\n\n"
                    f"Recommendations:\n" + "\n".join([f"- {r}" for r in report['recommendations']]) + "\n\n"
                    f"Full JSON report synced to Google Drive.\n"
                    f"Local path reference: {report_file}"
                )
                
                email_status = send_gmail_message(
                    to=email_recipient, 
                    subject=subject, 
                    body=body_text,
                    body_html=body_html
                )
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

    def _generate_intelligence_analysis(self, market_intel, cost_report, metrics, pending_debt) -> dict:
        """Uses LLM to synthesize all live data into a strategic intelligence report."""
        prompt = f"""
        Analyze the following live data from the Exegol autonomous fleet and generate a strategic intelligence report.
        
        MARKET INTELLIGENCE (Latest Trends):
        {json.dumps(market_intel)}
        
        COST REPORT (FinOps):
        Total Spend: ${cost_report.get('total_spend', 0)}
        Cloud Status: {cost_report.get('cloud_status', 'Unknown')}
        Remaining Quota: ${cost_report.get('remaining_quota', 0)}
        Provider Breakdown: {json.dumps(cost_report.get('provider_breakdown', {}))}
        
        FLEET HEALTH (Success Metrics):
        {json.dumps(metrics)}
        
        STRATEGIC DEBT (Pending HITL Tasks):
        Total Pending: {len(pending_debt)}
        Tasks: {json.dumps([t['task'] for t in pending_debt[:5]])}
        
        Return a JSON object with:
        1. "executive_summary": A 2-3 sentence strategic overview of the fleet's current state.
        2. "recommendations": A list of 3-5 actionable recommendations to improve cost efficiency, performance, or resolve strategic debt.
        """
        
        response = self.llm_client.generate(prompt, system_instruction=self.system_prompt, json_format=True)
        return self.llm_client.parse_json_response(response) or {
            "executive_summary": "Fleet nominal. Intelligence synthesis failed to provide deeper insights.",
            "recommendations": ["Review manual HITL queue.", "Monitor cloud spend trends."]
        }

    def _generate_html_report(self, report: dict) -> str:
        """Generates a premium HTML version of the intelligence report."""
        cost_rows = ""
        for agent, cost in report.get("cost_breakdown", {}).items():
            cost_rows += f"""
            <tr>
                <td style="padding: 12px; border-bottom: 1px solid #eee;">{agent}</td>
                <td style="padding: 12px; border-bottom: 1px solid #eee; text-align: right; font-family: monospace;">${cost:.4f}</td>
            </tr>
            """
        
        recs_list = "".join([f"<li style='margin-bottom: 8px;'>{r}</li>" for r in report.get("recommendations", [])])
        
        # Determine status color
        status = report.get('cloud_status', 'Healthy')
        status_color = "#2ecc71" if status == "Healthy" else "#f39c12" if status == "Near Limit" else "#e74c3c"
        
        # Fleet Health Section
        fleet_health_html = f"""
        <h2 style="color: #1a1a2e; font-size: 20px; border-bottom: 1px solid #eee; padding-bottom: 10px; margin-top: 40px;">Fleet Health</h2>
        <div style="display: flex; gap: 15px; margin-top: 15px;">
            <div style="flex: 1; background: #f8f9fa; padding: 15px; border-radius: 8px; text-align: center;">
                <span style="font-size: 11px; color: #999; text-transform: uppercase;">Avg Recall</span><br>
                <strong style="font-size: 20px; color: #2980b9;">{report.get('fleet_metrics', {}).get('fleet_recall', 0)*100:.1f}%</strong>
            </div>
            <div style="flex: 1; background: #f8f9fa; padding: 15px; border-radius: 8px; text-align: center;">
                <span style="font-size: 11px; color: #999; text-transform: uppercase;">Avg Precision</span><br>
                <strong style="font-size: 20px; color: #2980b9;">{report.get('fleet_metrics', {}).get('fleet_precision', 0)*100:.1f}%</strong>
            </div>
            <div style="flex: 1; background: #f8f9fa; padding: 15px; border-radius: 8px; text-align: center;">
                <span style="font-size: 11px; color: #999; text-transform: uppercase;">Pending Debt</span><br>
                <strong style="font-size: 20px; color: #e67e22;">{report.get('strategic_debt_count', 0)}</strong>
            </div>
        </div>
        """

        html = f"""
        <html>
        <body style="font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; color: #333; line-height: 1.6; max-width: 600px; margin: 0 auto; padding: 20px; border: 1px solid #eee; border-radius: 12px;">
            <div style="background: linear-gradient(135deg, #1a1a2e, #16213e); padding: 40px 20px; border-radius: 12px 12px 0 0; color: white; text-align: center;">
                <h1 style="margin: 0; font-size: 28px; letter-spacing: 1px;">EXEGOL INTELLIGENCE</h1>
                <p style="opacity: 0.7; margin-top: 10px; font-size: 14px; text-transform: uppercase; letter-spacing: 2px;">Weekly Fleet Audit & FinOps</p>
            </div>
            
            <div style="padding: 30px 20px;">
                <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 30px;">
                    <div>
                        <span style="font-size: 12px; color: #999; text-transform: uppercase; letter-spacing: 1px;">Status</span><br>
                        <strong style="color: {status_color}; font-size: 18px;">● {status}</strong>
                    </div>
                    <div style="text-align: right;">
                        <span style="font-size: 12px; color: #999; text-transform: uppercase; letter-spacing: 1px;">Total Spend</span><br>
                        <strong style="font-size: 18px;">${report.get('total_spend'):.4f}</strong>
                    </div>
                </div>

                <h2 style="color: #1a1a2e; font-size: 20px; border-bottom: 1px solid #eee; padding-bottom: 10px; margin-top: 40px;">Executive Summary</h2>
                <p style="font-size: 16px; color: #444; background: #f8f9fa; padding: 20px; border-left: 4px solid #1a1a2e; border-radius: 0 4px 4px 0;">
                    {report.get('summary')}
                </p>
                
                {fleet_health_html}

                <h2 style="color: #1a1a2e; font-size: 20px; border-bottom: 1px solid #eee; padding-bottom: 10px; margin-top: 40px;">Cost Breakdown</h2>
                <table style="width: 100%; border-collapse: collapse; margin-top: 10px;">
                    <thead>
                        <tr style="background: #f8f9fa;">
                            <th style="padding: 12px; text-align: left; font-size: 13px; color: #666; text-transform: uppercase;">Agent</th>
                            <th style="padding: 12px; text-align: right; font-size: 13px; color: #666; text-transform: uppercase;">Est. Cost</th>
                        </tr>
                    </thead>
                    <tbody>
                        {cost_rows}
                    </tbody>
                </table>
                
                <h2 style="color: #1a1a2e; font-size: 20px; border-bottom: 1px solid #eee; padding-bottom: 10px; margin-top: 40px;">Strategic Recommendations</h2>
                <ul style="padding-left: 20px; color: #444;">
                    {recs_list}
                </ul>
                
                <h2 style="color: #1a1a2e; font-size: 20px; border-bottom: 1px solid #eee; padding-bottom: 10px; margin-top: 40px;">Market Intelligence</h2>
                <div style="font-style: italic; color: #555; font-size: 14px; background: #eef2f7; padding: 20px; border-radius: 8px; line-height: 1.5;">
                    "{report.get('market_intel_snippet')[:400]}..."
                </div>
            </div>
            
            <div style="background: #fafafa; padding: 20px; text-align: center; font-size: 12px; color: #666; border-radius: 0 0 12px 12px; border-top: 1px solid #eee;">
                Generated by IntelImaAgent | Exegol V3 Autonomous Fleet
            </div>
        </body>
        </html>
        """
        return html
