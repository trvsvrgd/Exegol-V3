import os
import json
import re
import requests
from typing import Dict, Any, Optional, Union
from dotenv import load_dotenv

load_dotenv()

class LLMClient:
    """Unified client for interacting with local (Ollama) and cloud (Gemini) LLMs."""

    def __init__(self, provider: Optional[str] = None, model: Optional[str] = None):
        # Default to environment variables or local ollama
        self.provider = (provider or os.getenv("LLM_PROVIDER", "ollama")).lower()
        
        if self.provider == "ollama":
            self.model = model or os.getenv("OLLAMA_MODEL", "llama3")
            self.api_url = os.getenv("OLLAMA_URL", "http://localhost:11434/api/generate")
        else:
            self.model = model or os.getenv("GEMINI_MODEL", "gemini-1.5-pro")
            self.api_key = os.getenv("GEMINI_API_KEY")

    def generate(self, prompt: str, system_instruction: Optional[str] = None, json_format: bool = False) -> str:
        """Generates a completion from the configured provider."""
        if self.provider == "ollama":
            return self._generate_ollama(prompt, system_instruction, json_format)
        elif self.provider == "gemini":
            return self._generate_gemini(prompt, system_instruction, json_format)
        else:
            raise ValueError(f"Unknown provider: {self.provider}")

    def _generate_ollama(self, prompt: str, system_instruction: Optional[str], json_format: bool) -> str:
        full_system = system_instruction or "You are a helpful assistant."
        if json_format and "JSON" not in full_system:
            full_system += "\nReturn your response in strictly valid JSON format."

        payload = {
            "model": self.model,
            "prompt": prompt,
            "system": full_system,
            "stream": False,
            "format": "json" if json_format else ""
        }

        try:
            response = requests.post(self.api_url, json=payload, timeout=60)
            response.raise_for_status()
            return response.json().get("response", "")
        except Exception as e:
            return f"Error connecting to Ollama: {str(e)}"

    def _generate_gemini(self, prompt: str, system_instruction: Optional[str], json_format: bool) -> str:
        try:
            import google.generativeai as genai
            if not self.api_key:
                return "Error: GEMINI_API_KEY not found in environment."

            genai.configure(api_key=self.api_key)
            model = genai.GenerativeModel(
                model_name=self.model,
                system_instruction=system_instruction
            )
            
            generation_config = {}
            if json_format:
                generation_config["response_mime_type"] = "application/json"

            response = model.generate_content(
                prompt,
                generation_config=generation_config
            )
            return response.text
        except ImportError:
            return "Error: 'google-generativeai' package not installed."
        except Exception as e:
            return f"Error connecting to Gemini: {str(e)}"

    def parse_json_response(self, text: str) -> Dict[str, Any]:
        """Robustly extracts and parses JSON from a string, handling markdown wrappers."""
        if not text:
            return {}

        # Try to find JSON block in markdown
        json_match = re.search(r'```json\s*(.*?)\s*```', text, re.DOTALL)
        if json_match:
            clean_text = json_match.group(1)
        else:
            # Fallback: find first '{' and last '}'
            start = text.find('{')
            end = text.rfind('}')
            if start != -1 and end != -1:
                clean_text = text[start:end+1]
            else:
                clean_text = text

        try:
            return json.loads(clean_text)
        except json.JSONDecodeError as e:
            print(f"[LLMClient] Failed to parse JSON: {e}")
            print(f"[LLMClient] Raw text: {text[:200]}...")
            return {"error": "Invalid JSON format", "raw_content": text}

    def generate_system_prompt(self, agent: Any) -> str:
        """Generates a system prompt based on Agent Class attributes."""
        from inference.prompts import format_agent_prompt
        
        name = getattr(agent, "name", agent.__class__.__name__)
        description = agent.__class__.__doc__ or "A specialized autonomous agent."
        success_metrics = getattr(agent, "success_metrics", {})
        tools = getattr(agent, "tools", []) # Assuming agents might have a tools list
        
        return format_agent_prompt(name, description, success_metrics, tools)
