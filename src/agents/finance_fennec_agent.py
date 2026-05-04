import os
import json
import time
from tools.fleet_logger import log_interaction
from tools.web_search import web_search
from tools.cost_analyzer import CostAnalyzer
from tools.metrics_manager import SuccessMetricsManager

class FinanceFennecAgent:
    """Responsible for Economic Modeling & Monetization.
    
    Reads proposed business models and feature lists to output unit economics and financial projections.
    """

    def __init__(self, llm_client):
        self.llm_client = llm_client
        self.name = "FinanceFennecAgent"
        self.max_steps = 10
        self.tools = ["cost_analyzer", "web_search"]
        self.success_metrics = {
            "projection_accuracy": {
                "description": "Historical accuracy of cost projections vs actuals",
                "target": ">=90%",
                "current": None
            },
            "profitability_pathway": {
                "description": "Clear identification of break-even points in years",
                "target": "<=2",
                "current": None
            }
        }
        self.system_prompt = """
You are Finance Fennec, a mathematical and economic modeling expert within the Exegol v3 fleet.
Your core responsibility is 'Economic Modeling & Monetization.'

Your Directives:
1. Economic Inputs: Read the proposed business models from Sloane (strategy_brief.md) and the feature list from Poe.
2. Cost Analysis: Use the cost_analyzer to estimate cloud and API costs for the proposed features.
3. Financial Modeling: Generate .exegol/unit_economics.json containing:
   - Estimated Customer Acquisition Cost (CAC)
   - Lifetime Value (LTV) projections
   - Monthly burn rate based on infrastructure/API costs provided by Intel Ima
4. Handoff: Your output informs report_revan for the weekly fleet summary.

Tone: Precise, conservative, data-driven, and analytically rigorous.
"""
        self.metrics_manager = SuccessMetricsManager(os.getcwd())

    def execute(self, handoff):
        start_time = time.time()
        repo_path = handoff.repo_path
        print(f"[{self.name}] Session {handoff.session_id} — Modeling unit economics for repo: {repo_path}")

        exegol_dir = os.path.join(repo_path, ".exegol")
        brief_file = os.path.join(exegol_dir, "strategy_brief.md")
        economics_file = os.path.join(exegol_dir, "unit_economics.json")
        
        # Poe's features might be in the intent or backlog
        intent_file = os.path.join(exegol_dir, "intent.md")

        try:
            # 1. Read Inputs
            strategy_context = ""
            if os.path.exists(brief_file):
                with open(brief_file, 'r', encoding='utf-8') as f:
                    strategy_context = f.read()

            feature_context = ""
            if os.path.exists(intent_file):
                with open(intent_file, 'r', encoding='utf-8') as f:
                    feature_context = f.read()

            # 2. Analyze Costs
            print(f"[{self.name}] Analyzing projected infrastructure costs...")
            analyzer = CostAnalyzer(repo_path)
            current_costs = analyzer.get_current_usage()

            # 3. Research Market Benchmarks
            print(f"[{self.name}] Researching market benchmarks for CAC/LTV...")
            search_results = web_search("average CAC and LTV for SaaS and Marketplace 2025 benchmarks", num_results=3)

            # 4. Generate Unit Economics
            prompt = f"""
            Based on the strategy and feature context, and current infrastructure costs, generate unit economics projections.
            
            Strategy: {strategy_context}
            Features: {feature_context}
            Current Infrastructure Costs: {json.dumps(current_costs)}
            Market Benchmarks: {json.dumps(search_results)}
            
            Output a JSON object (.exegol/unit_economics.json) including:
            - customer_acquisition_cost_est
            - lifetime_value_projection
            - monthly_burn_rate
            - break_even_months
            """
            
            economics_json = self.llm_client.generate(prompt, system_instruction=self.system_prompt, json_format=True)
            
            # Basic validation/cleanup
            try:
                data = json.loads(economics_json)
                with open(economics_file, 'w', encoding='utf-8') as f:
                    json.dump(data, f, indent=4)
            except:
                with open(economics_file, 'w', encoding='utf-8') as f:
                    f.write(economics_json)

            res = f"Unit economics projections generated at {economics_file}. Handing off to report_revan."
            
            duration = time.time() - start_time
            log_interaction(
                agent_id=self.name,
                outcome="success",
                task_summary=res,
                repo_path=repo_path,
                steps_used=3,
                duration_seconds=duration,
                session_id=handoff.session_id
            )
            return res

        except Exception as e:
            duration = time.time() - start_time
            log_interaction(
                agent_id=self.name,
                outcome="failure",
                task_summary=f"Economics modeling failed: {str(e)}",
                repo_path=repo_path,
                steps_used=1,
                duration_seconds=duration,
                errors=[str(e)],
                session_id=handoff.session_id
            )
            return f"[{self.name}] Error: {e}"
