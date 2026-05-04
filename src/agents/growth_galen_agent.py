import os
import json
import time
from tools.fleet_logger import log_interaction
from tools.web_search import web_search
from tools.slack_tool import SlackTool
from tools.backlog_manager import BacklogManager
from tools.metrics_manager import SuccessMetricsManager

class GrowthGalenAgent:
    """Responsible for GTM Strategy & Brand Identity.
    
    Analyzes the strategy brief and generates a Go-To-Market plan, including outreach strategies
    and brand messaging.
    """

    def __init__(self, llm_client):
        self.llm_client = llm_client
        self.name = "GrowthGalenAgent"
        self.max_steps = 10
        self.tools = ["web_search", "slack_notifier", "backlog_writer"]
        self.success_metrics = {
            "lead_generation_potential": {
                "description": "Estimated number of high-quality leads targeted by the GTM plan",
                "target": ">=100",
                "current": None
            },
            "brand_consistency_score": {
                "description": "Alignment of brand messaging with strategy brief",
                "target": ">=90%",
                "current": None
            }
        }
        self.system_prompt = """
You are Growth Galen, an expert in user acquisition and brand building within the Exegol v3 fleet.
Your core responsibility is 'GTM Strategy & Brand Identity.'

Your Directives:
1. Analyze Strategy: Read .exegol/strategy_brief.md created by Sloane to understand the strategic direction.
2. GTM Planning: Perform web searches to identify high-traffic channels and LinkedIn outreach tactics.
3. Plan Generation: Generate .exegol/gtm_plan.md containing:
   - LinkedIn Outreach Strategy (Target personas, message templates)
   - 'Cold Start' User Acquisition Plan (Initial tactics to get the first 100 users)
   - Core Brand Messaging (Taglines, value propositions for the landing page)
4. Handoff: Your output informs markdown_mace for copy polishing. Visual assets are handled manually via screen capture or screenshots.

Tone: Energetic, persuasive, growth-oriented, and tactically precise.
"""
        self.metrics_manager = SuccessMetricsManager(os.getcwd())

    def execute(self, handoff):
        start_time = time.time()
        repo_path = handoff.repo_path
        print(f"[{self.name}] Session {handoff.session_id} — Developing GTM plan for repo: {repo_path}")

        exegol_dir = os.path.join(repo_path, ".exegol")
        brief_file = os.path.join(exegol_dir, "strategy_brief.md")
        gtm_file = os.path.join(exegol_dir, "gtm_plan.md")

        try:
            # 1. Read Strategy Brief
            strategy_brief = ""
            if os.path.exists(brief_file):
                with open(brief_file, 'r', encoding='utf-8') as f:
                    strategy_brief = f.read()
            else:
                print(f"[{self.name}] strategy_brief.md not found. Proceeding with general growth tactics.")
                strategy_brief = "Generic strategy brief based on repository structure."

            # 2. Research Growth Tactics
            print(f"[{self.name}] Researching user acquisition tactics...")
            search_results = web_search("effective LinkedIn outreach and cold start strategies 2025", num_results=5)

            # 3. Generate GTM Plan
            prompt = f"""
            Analyze the following strategy brief and research results to generate a Go-To-Market (GTM) Plan.
            
            Strategy Brief: {strategy_brief}
            Growth Research: {json.dumps(search_results)}
            
            Output a markdown file (.exegol/gtm_plan.md) that includes:
            - LinkedIn Outreach Strategy
            - 'Cold Start' User Acquisition Plan
            - Core Brand Messaging
            """
            
            gtm_plan = self.llm_client.generate(prompt, system_instruction=self.system_prompt)
            
            with open(gtm_file, 'w', encoding='utf-8') as f:
                f.write(gtm_plan)

            # 4. Notify Slack (Optional / Simulated)
            try:
                slack = SlackTool()
                slack.send_message(f"🚀 Growth Galen has finalized the GTM Plan for {os.path.basename(repo_path)}!")
            except Exception as e:
                print(f"[{self.name}] Slack notification skipped: {e}")

            res = f"GTM plan generated at {gtm_file}. Handing off to markdown_mace."
            
            duration = time.time() - start_time
            log_interaction(
                agent_id=self.name,
                outcome="success",
                task_summary=res,
                repo_path=repo_path,
                steps_used=2,
                duration_seconds=duration,
                session_id=handoff.session_id
            )
            return res

        except Exception as e:
            duration = time.time() - start_time
            log_interaction(
                agent_id=self.name,
                outcome="failure",
                task_summary=f"GTM plan generation failed: {str(e)}",
                repo_path=repo_path,
                steps_used=1,
                duration_seconds=duration,
                errors=[str(e)],
                session_id=handoff.session_id
            )
            return f"[{self.name}] Error: {e}"
