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
        elif routing_str == "gemini":
            return GeminiClient(model=model)
        elif routing_str in ("anthropic", "claude"):
            return AnthropicClient(model=model)
        elif routing_str == "vllm":
            return VLLMClient(model=model)
        elif routing_str == "llama.cpp":
            return LlamaCppClient(model=model)
        else:
            print(f"[InferenceManager] Treating '{routing_str}' as a specific Ollama local model.")
            # Use original case `provider` string for the model, as model names can be case sensitive
            return OllamaClient(model=provider)

    @staticmethod
    def check_vram_usage():
        """
        Placeholder for real VRAM monitoring logic.
        In a production implementation, this would query nvidia-smi or similar.
        """
        return "VRAM monitoring not yet implemented."
