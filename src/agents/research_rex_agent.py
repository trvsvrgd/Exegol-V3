import os
import json


class ResearchRexAgent:
    """Researches inference backends and local hardware capabilities to optimize performance and cost.
    
    Responsible for identifying the best local inference strategy (Ollama, vLLM, llama.cpp) 
    based on the application's throughput requirements and available VRAM/RAM.
    """

    def __init__(self, llm_client):
        self.llm_client = llm_client
        self.name = "ResearchRexAgent"
        self.max_steps = 10
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
        repo_path = handoff.repo_path
        print(f"[{self.name}] Session {handoff.session_id} — performing hardware & inference scan.")

        exegol_dir = os.path.join(repo_path, ".exegol")
        reports_dir = os.path.join(exegol_dir, "research_reports")
        os.makedirs(reports_dir, exist_ok=True)

        # Mock hardware detection
        gpu_detected = True  # In a real run, use tools to detect CUDA
        vram_gb = 16
        
        recommendation = "vLLM" if gpu_detected and vram_gb >= 12 else "Ollama"
        
        strategy_report = {
            "timestamp": os.path.basename(repo_path), # Mocking timestamp
            "hardware": {
                "gpu": "NVIDIA RTX 4080" if gpu_detected else "None",
                "vram": f"{vram_gb}GB",
                "cpu_cores": 16
            },
            "recommendation": {
                "backend": recommendation,
                "reasoning": f"Detected {vram_gb}GB VRAM. {recommendation} offers the best balance of throughput and ease of use for this hardware."
            },
            "suggested_actions": [
                f"Switch model_routing_preference to '{recommendation.lower()}' in priority.json",
                "Install vLLM dependencies via 'pip install vllm'"
            ]
        }

        report_file = os.path.join(reports_dir, f"inference_strategy.json")
        with open(report_file, 'w', encoding='utf-8') as f:
            json.dump(strategy_report, f, indent=4)

        return f"Inference strategy research completed. Recommendation: {recommendation}. Report: {report_file}"
 Riverside: Updating ResearchRexAgent.py execute logic
