import os
from typing import Optional
from inference.llm_client import LLMClient, OllamaClient, GeminiClient, VLLMClient, LlamaCppClient

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
        provider = (provider or os.getenv("LLM_PROVIDER", "ollama")).lower()
        
        if provider == "ollama":
            return OllamaClient(model=model)
        elif provider == "gemini":
            return GeminiClient(model=model)
        elif provider == "vllm":
            return VLLMClient(model=model)
        elif provider == "llama.cpp":
            return LlamaCppClient(model=model)
        else:
            print(f"[InferenceManager] Warning: Unknown provider '{provider}'. Defaulting to Ollama.")
            return OllamaClient(model=model)

    @staticmethod
    def check_vram_usage():
        """
        Placeholder for real VRAM monitoring logic.
        In a production implementation, this would query nvidia-smi or similar.
        """
        return "VRAM monitoring not yet implemented."
