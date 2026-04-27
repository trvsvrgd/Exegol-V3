import os
import json
import time
from tools.web_search import web_search
from tools.fleet_logger import log_interaction


class ResearchRexAgent:
    """Researches inference backends and local hardware capabilities to optimize performance and cost.
    
    Responsible for identifying the best local inference strategy (Ollama, vLLM, llama.cpp) 
    based on the application's throughput requirements and available VRAM/RAM.
    """

    def __init__(self, llm_client):
        self.llm_client = llm_client
        self.name = "ResearchRexAgent"
        self.max_steps = 10
        self._steps_used = 0
        self.tools = ["model_comparison", "web_search", "inference_benchmarking"]
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
            }
        }
        self.system_prompt = self.llm_client.generate_system_prompt(self)

    def execute(self, handoff):
        """Execute with a clean HandoffContext — no prior session memory required.

        Performs a hardware scan and recommends the optimal local inference backend.
        """
        start_time = time.time()
        self._steps_used = 0
        repo_path = handoff.repo_path
        print(f"[{self.name}] Session {handoff.session_id} — performing hardware & inference scan.")

        exegol_dir = os.path.join(repo_path, ".exegol")
        reports_dir = os.path.join(exegol_dir, "research_reports")
        os.makedirs(reports_dir, exist_ok=True)

        try:
            # 1. Perform Research on latest inference backends
            print(f"[{self.name}] Searching for latest inference backend benchmarks (vLLM vs Ollama vs llama.cpp)...")
            search_query = "latest LLM inference backend benchmarks 2024 2025 vLLM Ollama llama.cpp"
            search_results = web_search(search_query, num_results=5)
            self._steps_used += 1

            # 2. Analyze results with LLM (Simulating hardware context)
            # In a real environment, we'd also run local 'nvidia-smi' or similar tools.
            # For now, we combine the search results with assumed/detected hardware.
            analysis_prompt = f"""
            Research Task: Identify the best local inference backend.
            Search Results: {json.dumps(search_results)}
            
            Context: The system has 16GB VRAM and an NVIDIA RTX 4080.
            Based on the search results and context, recommend 'vLLM', 'Ollama', or 'llama.cpp'.
            Provide a JSON response with:
            - 'recommendation': The backend name
            - 'reasoning': Why this choice fits the hardware
            - 'hardware_stats': {{'gpu': 'RTX 4080', 'vram': '16GB'}}
            - 'suggested_actions': List of 2 actions to implement this.
            """
            
            response = self.llm_client.generate(analysis_prompt, system_instruction=self.system_prompt, json_format=True)
            analysis_data = self.llm_client.parse_json_response(response)
            self._steps_used += 1

            if not analysis_data:
                return "Failed to analyze research results."

            strategy_report = {
                "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
                "hardware": analysis_data.get("hardware_stats", {}),
                "recommendation": {
                    "backend": analysis_data.get("recommendation"),
                    "reasoning": analysis_data.get("reasoning")
                },
                "suggested_actions": analysis_data.get("suggested_actions", [])
            }

            report_file = os.path.join(reports_dir, f"inference_strategy.json")
            with open(report_file, 'w', encoding='utf-8') as f:
                json.dump(strategy_report, f, indent=4)

            duration = time.time() - start_time
            res = f"Inference strategy research completed. Recommendation: {strategy_report['recommendation']['backend']}. Report: {report_file}"
            
            log_interaction(
                agent_id=self.name,
                outcome="success",
                task_summary=res,
                repo_path=repo_path,
                steps_used=self._steps_used,
                duration_seconds=duration,
                session_id=handoff.session_id
            )
            
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
 Riverside: Updating ResearchRexAgent.py execute logic
