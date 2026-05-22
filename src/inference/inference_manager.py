import os
from typing import Optional
from inference.llm_client import LLMClient, OllamaClient, GeminiClient, VLLMClient, LlamaCppClient, AnthropicClient

class InferenceManager:
    """
    Central orchestrator for selecting and managing multiple inference backends.
    Allows Exegol to stay provider-agnostic and scale from local to production.
    """

    @staticmethod
    def get_client(provider: Optional[str] = None, model: Optional[str] = None) -> LLMClient:
        """
        Factory method to return the appropriate LLM client based on provider type.
        Defaults to environment variables or local Ollama.
        """
        routing_str = (provider or os.getenv("LLM_PROVIDER", "ollama")).lower()
        
        if routing_str == "ollama":
            return OllamaClient(model=model)
        elif routing_str == "gemini" or routing_str.startswith("gemini-") or routing_str.startswith("gemini/"):
            # If the provider string specifies a model, use it as the model name if no model is explicitly passed
            chosen_model = model or (provider if routing_str != "gemini" else None)
            return GeminiClient(model=chosen_model)
        elif (routing_str in ("anthropic", "claude") or 
              routing_str.startswith("anthropic-") or routing_str.startswith("claude-") or
              routing_str.startswith("anthropic/") or routing_str.startswith("claude/")):
            chosen_model = model or (provider if routing_str not in ("anthropic", "claude") else None)
            return AnthropicClient(model=chosen_model)
        elif routing_str == "vllm" or routing_str.startswith("vllm-") or routing_str.startswith("vllm/"):
            chosen_model = model or (provider if routing_str != "vllm" else None)
            return VLLMClient(model=chosen_model)
        elif routing_str == "llama.cpp":
            return LlamaCppClient(model=model)
        else:
            print(f"[InferenceManager] Treating '{routing_str}' as a specific Ollama local model.")
            # Use original case `provider` string for the model, as model names can be case sensitive
            return OllamaClient(model=provider)

    @staticmethod
    def check_vram_usage():
        """
        Uses HardwareScanner to retrieve real VRAM monitoring data.
        """
        try:
            from tools.hardware_scanner import HardwareScanner
            scanner = HardwareScanner()
            profile = scanner.scan()
            gpu = profile.get("gpu", {})
            if gpu.get("detected"):
                total = gpu.get("vram_total_mb", 0)
                free = gpu.get("vram_free_mb", 0)
                used = total - free
                return {
                    "status": "success",
                    "vram_total_mb": total,
                    "vram_free_mb": free,
                    "vram_used_mb": used,
                    "usage_percent": round((used / total) * 100, 2) if total > 0 else 0
                }
            return {"status": "error", "message": gpu.get("reason", "GPU not detected")}
        except Exception as e:
            return {"status": "error", "message": str(e)}
