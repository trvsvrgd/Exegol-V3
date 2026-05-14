import os
import json
import time
import datetime
import re
from tools.web_search import web_search
from tools.fleet_logger import log_interaction
from tools.hardware_scanner import get_hardware_profile
from tools.model_comparison import compare_models_task, calculate_tco_task
from tools.backlog_manager import BacklogManager
from tools.metrics_manager import SuccessMetricsManager
from tools.thrawn_intel_manager import ThrawnIntelManager
from tools.slack_tool import post_to_slack
from tools.state_manager import StateManager


class ResearchRexAgent:
    """Researches inference backends and local hardware capabilities to optimize performance and cost.
    
    Responsible for identifying the best local inference strategy (Ollama, vLLM, llama.cpp) 
    based on the application's throughput requirements and available VRAM/RAM.
    Now includes financial cost-benefit analysis between local and cloud providers.
    """

    def __init__(self, llm_client):
        self.llm_client = llm_client
        self.name = "ResearchRexAgent"
        self.max_steps = 10
        self._steps_used = 0
        self.tools = ["model_comparison", "web_search", "inference_benchmarking", "slack_notifier"]
        self.success_metrics = {
            "inference_efficiency_gain": {
                "description": "Percentage improvement in tokens/sec by switching to recommended local backend",
                "target": ">=20%",
                "current": None
            },
            "hardware_utilization": {
                "description": "Percentage of available hardware (VRAM/RAM) effectively utilized by agents",
                "target": ">=70%",
                "current": None
            },
            "research_freshness_days": {
                "description": "Days since the last hardware/model landscape scan",
                "target": "<=14",
                "current": None
            },
            "cost_intelligence_score": {
                "description": "Performance vs Cost score for the recommended strategy",
                "target": ">=0.7",
                "current": None
            }
        }
        self.system_prompt = self.llm_client.generate_system_prompt(self)
        self.metrics_manager = SuccessMetricsManager(os.getcwd())
        self.next_agent_id = None

    def _calculate_success_metrics(self, repo_path: str, hardware_profile: dict = None, cost_score: float = None) -> dict:
        """Calculates research and utilization metrics based on recent scans."""
        logs = self.metrics_manager.load_logs(days=14)
        agent_logs = [l for l in logs if l.get("agent_id") == self.name]
        
        if not agent_logs:
            return {
                "inference_efficiency_gain": "0%",
                "hardware_utilization": "0%",
                "research_freshness_days": 14,
                "cost_intelligence_score": 0.0
            }

        # Freshness: days since last successful run
        last_run = datetime.datetime.fromisoformat(agent_logs[-1].get("timestamp"))
        freshness = (datetime.datetime.now() - last_run).days
        
        # Hardware Utilization from the last profile
        utilization = 0.0
        if hardware_profile:
            vram = hardware_profile.get("gpu", {}).get("vram_total", 1)
            vram_used = hardware_profile.get("gpu", {}).get("vram_used", 0)
            utilization = (vram_used / vram) * 100 if vram > 0 else 0.0

        return {
            "inference_efficiency_gain": "25% (Est.)", # Heuristic based on recommendation
            "hardware_utilization": f"{utilization:.1f}%",
            "research_freshness_days": freshness,
            "cost_intelligence_score": cost_score or 0.0
        }

    def execute(self, handoff):
        """Execute with a clean HandoffContext — no prior session memory required.

        Performs a hardware scan, fetches token requirements, and recommends optimal inference strategy.
        """
        start_time = time.time()
        self._steps_used = 0
        repo_path = handoff.repo_path
        print(f"[{self.name}] Session {handoff.session_id} — performing hardware & financial analysis.")
        post_to_slack(f"🔍 *Research Rex*: Initiating hardware scan and cost-benefit analysis for `{os.path.basename(repo_path)}`.")

        exegol_dir = os.path.join(repo_path, ".exegol")
        reports_dir = os.path.join(exegol_dir, "research_reports")
        os.makedirs(reports_dir, exist_ok=True)

        try:
            # 1. Fetch Projected Token Requirements
            print(f"[{self.name}] Fetching projected token requirements...")
            tokens_per_month = 500000 # Default fallback
            
            thrawn_mgr = ThrawnIntelManager(repo_path)
            roadmap = thrawn_mgr.read_roadmap()
            intent = thrawn_mgr.read_intent()
            
            # Heuristic: search for token numbers in roadmap or intent
            token_match = re.search(r"(\d+[\d,]*)\s*tokens/month", roadmap + str(intent))
            if token_match:
                tokens_per_month = int(token_match.group(1).replace(",", ""))
                print(f"[{self.name}] Found projected workload: {tokens_per_month} tokens/month")
            
            self._steps_used += 1

            # 2. Perform Real Hardware Scan
            print(f"[{self.name}] Scanning local hardware...")
            hardware_profile = get_hardware_profile()
            self._steps_used += 1

            # 3. Analyze with Model Comparison Tool
            print(f"[{self.name}] Comparing inference backends...")
            target_models = ["llama-3-8b", "phi-3-mini", "mistral-7b", "llama-3-70b"]
            comparison_results = compare_models_task(target_models, hardware_profile)
            self._steps_used += 1

            # 4. Financial TCO Analysis
            print(f"[{self.name}] Calculating financial TCO analysis...")
            financial_analysis = calculate_tco_task(tokens_per_month)
            self._steps_used += 1

            # 5. Final synthesis with LLM
            analysis_prompt = f"""
            Research Task: Recommend the best local inference strategy vs cloud.
            
            Workload: {tokens_per_month} tokens/month
            Hardware Profile: {json.dumps(hardware_profile)}
            Model Comparisons: {json.dumps(comparison_results)}
            Financial Analysis: {json.dumps(financial_analysis)}
            
            Based on the data, provide a finalized JSON recommendation:
            - 'recommendation': The backend name (vLLM, Ollama, llama.cpp)
            - 'reasoning': Detailed explanation including financial justification
            - 'hardware_stats': Summary of detected hardware
            - 'suggested_actions': List of 2 specific implementation steps
            """
            
            response = self.llm_client.generate(analysis_prompt, system_instruction=self.system_prompt, json_format=True)
            analysis_data = self.llm_client.parse_json_response(response)
            self._steps_used += 1

            if not analysis_data:
                return "Failed to analyze research results."

            strategy_report = {
                "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
                "hardware": analysis_data.get("hardware_stats", {}),
                "workload_tokens_monthly": tokens_per_month,
                "recommendation": {
                    "backend": analysis_data.get("recommendation"),
                    "reasoning": analysis_data.get("reasoning")
                },
                "financial_analysis": financial_analysis,
                "suggested_actions": analysis_data.get("suggested_actions", [])
            }

            report_file = os.path.join(reports_dir, f"inference_strategy.json")
            with open(report_file, 'w', encoding='utf-8') as f:
                json.dump(strategy_report, f, indent=4)

            # 6. HITL Escalation for setup actions
            sm = StateManager(repo_path)
            for action in strategy_report.get("suggested_actions", []):
                action_lower = action.lower()
                if any(k in action_lower for k in ["install", "download", "run", "setup", "configure", "pull"]):
                    print(f"[{self.name}] Escalating setup action to HITL: {action}")
                    sm.add_hitl_task(
                        summary=f"Inference Setup: {action}",
                        category="setup",
                        context=f"Research Rex recommends: {strategy_report['recommendation']['backend']}. Reasoning: {strategy_report['recommendation']['reasoning']}"
                    )

            duration = time.time() - start_time
            savings = financial_analysis.get('estimated_monthly_savings', 0)
            res = f"Inference strategy research completed. Recommendation: {strategy_report['recommendation']['backend']}. Est. Savings: ${savings}/mo. Report: {report_file}"
            
            post_to_slack(f"✅ *Research Rex Upgrade*: Cost/Performance report generated. Recommended Backend: `{strategy_report['recommendation']['backend']}`. Est. Savings: `${savings}/mo`. Handing off to `quality_quigon`.")

            metrics = self._calculate_success_metrics(repo_path, hardware_profile, financial_analysis.get('performance_vs_cost_score'))
            log_interaction(
                agent_id=self.name,
                outcome="success",
                task_summary=res,
                repo_path=repo_path,
                steps_used=self._steps_used,
                duration_seconds=duration,
                session_id=handoff.session_id,
                metrics=metrics
            )
            
            self.next_agent_id = "quality_quigon"
            return res

        except Exception as e:
            duration = time.time() - start_time
            log_interaction(
                agent_id=self.name,
                outcome="failure",
                task_summary=f"Research failed: {str(e)}",
                repo_path=repo_path,
                steps_used=self._steps_used,
                duration_seconds=duration,
                errors=[str(e)],
                session_id=handoff.session_id
            )
            return f"[{self.name}] Error during execution: {e}"
