import json
import os
from typing import List, Dict, Any
from tools.cost_analyzer import DEFAULT_PRICING

class ModelComparisonTool:
    """Evaluates model compatibility with local hardware and compares performance/cost benchmarks."""

    def __init__(self):
        # Heuristic VRAM requirements (in GB) for 4-bit (Q4_K_M) quantization
        self.vram_heuristics = {
            "1.5b": 1.5,
            "3b": 2.5,
            "7b": 5.5,
            "8b": 6.0,
            "13b": 9.5,
            "14b": 10.5,
            "30b": 22.0,
            "70b": 45.0
        }
        self.pricing = self._load_pricing()

    def _load_pricing(self) -> Dict[str, Dict[str, float]]:
        """Loads pricing table — uses defaults (override via config/pricing.json if present)."""
        repo_path = os.getcwd()
        pricing_path = os.path.join(repo_path, "config", "pricing.json")
        if os.path.exists(pricing_path):
            try:
                with open(pricing_path, "r", encoding="utf-8") as f:
                    custom = json.load(f)
                merged = dict(DEFAULT_PRICING)
                merged.update(custom)
                return merged
            except Exception:
                pass
        return dict(DEFAULT_PRICING)

    def calculate_projected_cost(self, tokens_per_month: int, backend: str) -> float:
        """Calculates estimated monthly cost for a given backend based on token volume.
        
        Args:
            tokens_per_month (int): Total expected tokens (input + output).
            backend (str): Model key or backend name (e.g., 'gemini', 'gpt-4o', 'ollama').
            
        Returns:
            float: Estimated monthly USD cost.
        """
        backend_lower = backend.lower()
        
        # Resolve model key (similar logic to CostAnalyzer)
        model_key = "default"
        for key in self.pricing:
            if key in backend_lower:
                model_key = key
                break
        
        if "ollama" in backend_lower or "local" in backend_lower or "vllm" in backend_lower:
            model_key = "ollama"

        pricing = self.pricing.get(model_key, self.pricing["default"])
        
        # Assume 70/30 split as per CostAnalyzer
        input_tokens = tokens_per_month * 0.70
        output_tokens = tokens_per_month * 0.30
        
        input_cost = (input_tokens / 1_000_000) * pricing["input"]
        output_cost = (output_tokens / 1_000_000) * pricing["output"]
        
        return round(input_cost + output_cost, 4)

    def compare_tco(self, tokens_per_month: int, cloud_backends: List[str] = ["gemini", "gpt-4o"]) -> Dict[str, Any]:
        """Compares Total Cost of Ownership between local and cloud backends.
        
        Returns:
            Dict containing comparison data, estimated savings, and performance scores.
        """
        local_cost = self.calculate_projected_cost(tokens_per_month, "ollama")
        
        cloud_analysis = {}
        max_savings = 0.0
        
        for backend in cloud_backends:
            cost = self.calculate_projected_cost(tokens_per_month, backend)
            savings = cost - local_cost
            cloud_analysis[backend] = {
                "estimated_monthly_cost": cost,
                "potential_savings": savings
            }
            if savings > max_savings:
                max_savings = savings

        return {
            "workload_tokens_monthly": tokens_per_month,
            "local_inference": {
                "cost": local_cost,
                "status": "Free (excluding electricity/hardware)"
            },
            "cloud_providers": cloud_analysis,
            "estimated_monthly_savings": round(max_savings, 2),
            "performance_vs_cost_score": self._calculate_performance_score(tokens_per_month, max_savings)
        }

    def _calculate_performance_score(self, tokens: int, savings: float) -> float:
        """Heuristic score (0.0 - 1.0) for performance vs cost efficiency."""
        if tokens == 0: return 1.0
        # Heuristic: Savings of $50+ on a significant workload is high efficiency
        score = min(1.0, (savings / 100.0) + 0.5) if savings > 0 else 0.2
        return round(score, 2)

    def compare_models(self, models: List[str], hardware_profile: Dict[str, Any]) -> Dict[str, Any]:
        """Compares models against the provided hardware profile."""
        vram_total = hardware_profile.get("gpu", {}).get("vram_total_mb", 0) / 1024.0
        results = {}

        for model in models:
            model_size = self._parse_size(model)
            required_vram = self.vram_heuristics.get(model_size, 0)
            
            can_run = vram_total >= required_vram if required_vram > 0 else "unknown"
            
            results[model] = {
                "size_class": model_size,
                "estimated_vram_gb": required_vram,
                "compatibility": "Compatible" if can_run == True else ("Incompatible" if can_run == False else "Unknown"),
                "notes": f"Requires ~{required_vram}GB for 4-bit quant" if required_vram > 0 else "No heuristic available"
            }

        return results

    def _parse_size(self, model_name: str) -> str:
        """Extracts size class from model name (e.g. 'llama-3-8b' -> '8b')."""
        import re
        match = re.search(r'(\d+(\.\d+)?[bB])', model_name)
        if match:
            return match.group(1).lower()
        return "unknown"

    def recommend_backend(self, hardware_profile: Dict[str, Any], load_requirement: str = "balanced") -> Dict[str, Any]:
        """Recommends an inference backend based on hardware and requirements."""
        gpu = hardware_profile.get("gpu", {})
        
        if gpu.get("detected"):
            vram = gpu.get("vram_total_mb", 0) / 1024.0
            if vram >= 24:
                return {
                    "backend": "vLLM",
                    "reason": "High VRAM detected. vLLM offers superior throughput for high-end GPUs."
                }
            elif vram >= 8:
                return {
                    "backend": "Ollama",
                    "reason": "Sufficient VRAM for most models. Ollama provides the best balance of ease-of-use and performance."
                }
            else:
                return {
                    "backend": "llama.cpp (via Ollama)",
                    "reason": "Low VRAM. llama.cpp quantization and CPU offloading are recommended."
                }
        else:
            return {
                "backend": "llama.cpp",
                "reason": "No NVIDIA GPU detected. CPU-only inference via llama.cpp is the only local option."
            }

def compare_models_task(models: List[str], hardware_profile: Dict[str, Any]) -> Dict[str, Any]:
    tool = ModelComparisonTool()
    return {
        "comparisons": tool.compare_models(models, hardware_profile),
        "recommendation": tool.recommend_backend(hardware_profile)
    }

def calculate_tco_task(tokens_per_month: int, cloud_backends: List[str] = ["gemini", "gpt-4o"]) -> Dict[str, Any]:
    tool = ModelComparisonTool()
    return tool.compare_tco(tokens_per_month, cloud_backends)
