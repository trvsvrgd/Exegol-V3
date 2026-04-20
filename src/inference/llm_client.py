import os
import json
import re
import requests
from abc import ABC, abstractmethod
from typing import Dict, Any, Optional, Union
from dotenv import load_dotenv

load_dotenv()

class LLMClient(ABC):
    """Abstract base class for all inference providers."""
    
    def __init__(self, model: str):
        self.model = model

    @abstractmethod
    def generate(self, prompt: str, system_instruction: Optional[str] = None, json_format: bool = False) -> str:
        pass

    def generate_system_prompt(self, agent: Any) -> str:
        """Generates a system prompt based on Agent Class attributes."""
        from inference.prompts import format_agent_prompt
        
        name = getattr(agent, "name", agent.__class__.__name__)
        description = agent.__class__.__doc__ or "A specialized autonomous agent."
        success_metrics = getattr(agent, "success_metrics", {})
        tools = getattr(agent, "tools", [])
        
        return format_agent_prompt(name, description, success_metrics, tools)

    def parse_json_response(self, text: str) -> Dict[str, Any]:
        """Robustly extracts and parses JSON from a string."""
        if not text: return {}
        json_match = re.search(r'```json\s*(.*?)\s*```', text, re.DOTALL)
        clean_text = json_match.group(1) if json_match else text
        try:
            return json.loads(clean_text)
        except:
            # Fallback extraction logic
            start, end = text.find('{'), text.rfind('}')
            if start != -1 and end != -1:
                try: return json.loads(text[start:end+1])
                except: pass
            return {"error": "Invalid JSON", "raw": text}

class OllamaClient(LLMClient):
    def __init__(self, model: Optional[str] = None):
        super().__init__(model or os.getenv("OLLAMA_MODEL", "llama3"))
        self.api_url = os.getenv("OLLAMA_URL", "http://localhost:11434/api/generate")

    def generate(self, prompt: str, system_instruction: Optional[str] = None, json_format: bool = False) -> str:
        payload = {
            "model": self.model,
            "prompt": prompt,
            "system": system_instruction or "You are a helpful assistant.",
            "stream": False,
            "format": "json" if json_format else ""
        }
        try:
            response = requests.post(self.api_url, json=payload, timeout=60)
            return response.json().get("response", "")
        except Exception as e:
            return f"Ollama Error: {e}"

class GeminiClient(LLMClient):
    def __init__(self, model: Optional[str] = None):
        super().__init__(model or os.getenv("GEMINI_MODEL", "gemini-1.5-pro"))
        self.api_key = os.getenv("GEMINI_API_KEY")

    def generate(self, prompt: str, system_instruction: Optional[str] = None, json_format: bool = False) -> str:
        try:
            import google.generativeai as genai
            genai.configure(api_key=self.api_key)
            model = genai.GenerativeModel(self.model, system_instruction=system_instruction)
            config = {"response_mime_type": "application/json"} if json_format else {}
            return model.generate_content(prompt, generation_config=config).text
        except Exception as e:
            return f"Gemini Error: {e}"

class VLLMClient(LLMClient):
    """Placeholder for high-throughput vLLM backend."""
    def generate(self, prompt: str, system_instruction: Optional[str] = None, json_format: bool = False) -> str:
        return "vLLM Provider not yet implemented."

class LlamaCppClient(LLMClient):
    """Placeholder for memory-efficient llama.cpp backend."""
    def generate(self, prompt: str, system_instruction: Optional[str] = None, json_format: bool = False) -> str:
        return "llama.cpp Provider not yet implemented."
