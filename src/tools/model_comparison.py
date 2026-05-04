import json
from typing import List, Dict, Any

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
        ram = hardware_profile.get("ram", {})
        
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
