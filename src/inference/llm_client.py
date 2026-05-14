import os
import json
import re
import datetime
import requests
from urllib.parse import urlparse
from abc import ABC, abstractmethod
from typing import Dict, Any, Optional, Union
from dotenv import load_dotenv
from tools.egress_filter import EgressFilter

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

    def parse_json_response(self, text: str) -> Union[dict[str, Any], list[Any]]:
        """Robustly extracts and parses JSON from a string (objects or arrays)."""
        if not text: return {}
        # Strip markdown code fences
        json_match = re.search(r'```json\s*(.*?)\s*```', text, re.DOTALL)
        clean_text = json_match.group(1) if json_match else text.strip()
        
        def unwrap_if_needed(obj):
            if isinstance(obj, dict):
                # Auto-unwrap common patterns: {"actions": [...]} or {"plan": [...]}
                if "actions" in obj and isinstance(obj["actions"], list):
                    return obj["actions"]
                if "plan" in obj and isinstance(obj["plan"], list):
                    return obj["plan"]
                # If it's a single action object, wrap it in a list
                if "type" in obj and ("path" in obj or "file" in obj or "target" in obj):
                    return [obj]
            return obj

        # Try direct parse first
        try:
            obj = json.loads(clean_text)
            return unwrap_if_needed(obj)
        except Exception:
            pass
        # Try extracting a JSON array [...]
        arr_start, arr_end = clean_text.find('['), clean_text.rfind(']')
        if arr_start != -1 and arr_end != -1:
            try:
                obj = json.loads(clean_text[arr_start:arr_end+1])
                return unwrap_if_needed(obj)
            except Exception:
                pass
        # Try extracting a JSON object {...}
        start, end = clean_text.find('{'), clean_text.rfind('}')
        if start != -1 and end != -1:
            try: 
                obj = json.loads(clean_text[start:end+1])
                return unwrap_if_needed(obj)
            except: pass
        return {"error": "Invalid JSON", "raw": text}

class TrackingLLMClient(LLMClient):
    """Wraps an LLMClient to track usage metrics."""
    def __init__(self, base_client: LLMClient):
        super().__init__(base_client.model)
        self.base_client = base_client
        self.prompt_count = 0
        self.token_usage = 0
        self.history = []

    def generate(self, prompt: str, system_instruction: Optional[str] = None, json_format: bool = False) -> str:
        self.prompt_count += 1
        # Simple heuristic: 1 token ~= 4 characters for now
        self.token_usage += (len(prompt) + (len(system_instruction) if system_instruction else 0)) // 4
        
        response = self.base_client.generate(prompt, system_instruction, json_format)
        
        # Add response tokens
        self.token_usage += len(response) // 4
        
        # Log to history
        self.history.append({
            "timestamp": datetime.datetime.now().isoformat(),
            "system_instruction": system_instruction,
            "prompt": prompt,
            "response": response
        })
        
        return response

    def generate_system_prompt(self, agent: Any) -> str:
        return self.base_client.generate_system_prompt(agent)

class OllamaClient(LLMClient):
    def __init__(self, model: Optional[str] = None):
        super().__init__(model or os.getenv("OLLAMA_MODEL", "llama3"))
        self.api_url = os.getenv("OLLAMA_URL", "http://localhost:11434/api/generate")
        self._allowed_hosts = {"localhost", "127.0.0.1", "host.docker.internal"}

    def _validate_url(self, url: str) -> bool:
        """Ensures the URL is within the allowed set of hosts to prevent SSRF."""
        return EgressFilter.is_url_allowed(url)

    def generate(self, prompt: str, system_instruction: Optional[str] = None, json_format: bool = False) -> str:
        payload = {
            "model": self.model,
            "prompt": prompt,
            "system": system_instruction or "You are a helpful assistant.",
            "stream": False,
            "format": "json" if json_format else ""
        }
        try:
            if not self._validate_url(self.api_url):
                return f"Security Error: Blocked attempt to access non-allowlisted host in Ollama URL: {self.api_url}"
                
            response = requests.post(self.api_url, json=payload, timeout=60)
            return response.json().get("response", "")
        except Exception as e:
            return f"Ollama Error: {e}"

class GeminiClient(LLMClient):
    def __init__(self, model: Optional[str] = None):
        super().__init__(model or os.getenv("GEMINI_MODEL", "gemini-2.0-flash"))
        self.api_key = os.getenv("GEMINI_API_KEY")

    def generate(self, prompt: str, system_instruction: Optional[str] = None, json_format: bool = False) -> str:
        try:
            EgressFilter.validate_request("https://generativelanguage.googleapis.com")
            # Try new google.genai SDK first
            try:
                from google import genai
                from google.genai import types
                client = genai.Client(api_key=self.api_key)
                config_kwargs = {}
                if json_format:
                    config_kwargs["response_mime_type"] = "application/json"
                if system_instruction:
                    config_kwargs["system_instruction"] = system_instruction
                response = client.models.generate_content(
                    model=self.model,
                    contents=prompt,
                    config=types.GenerateContentConfig(**config_kwargs) if config_kwargs else None,
                )
                return response.text
            except Exception as new_sdk_err:
                # Fall back to deprecated google.generativeai if new SDK fails
                print(f"[GeminiClient] New SDK failed ({new_sdk_err}), falling back to google.generativeai")
                import google.generativeai as genai_legacy
                genai_legacy.configure(api_key=self.api_key)
                model_obj = genai_legacy.GenerativeModel(self.model, system_instruction=system_instruction)
                config = {"response_mime_type": "application/json"} if json_format else {}
                return model_obj.generate_content(prompt, generation_config=config).text
        except Exception as e:
            return f"Gemini Error: {e}"

class VLLMClient(LLMClient):
    """Client for high-throughput vLLM backend, following OpenAI API standards."""
    def __init__(self, model: Optional[str] = None):
        super().__init__(model or os.getenv("VLLM_MODEL", "facebook/opt-125m"))
        self.api_url = os.getenv("VLLM_URL", "http://localhost:8000/v1/chat/completions")
        self.api_key = os.getenv("VLLM_API_KEY", "EMPTY")

    def generate(self, prompt: str, system_instruction: Optional[str] = None, json_format: bool = False) -> str:
        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system_instruction or "You are a helpful assistant."},
                {"role": "user", "content": prompt}
            ],
            "temperature": 0.7,
            "max_tokens": 4096
        }
        try:
            if not EgressFilter.is_url_allowed(self.api_url):
                return f"Security Error: Blocked attempt to access non-allowlisted host in vLLM URL: {self.api_url}"
                
            response = requests.post(
                self.api_url, 
                json=payload, 
                headers={"Authorization": f"Bearer {self.api_key}"},
                timeout=120
            )
            data = response.json()
            return data.get("choices", [{}])[0].get("message", {}).get("content", "")
        except Exception as e:
            return f"vLLM Error: {e}"

class LlamaCppClient(LLMClient):
    """Client for memory-efficient llama.cpp backend, following OpenAI API standards."""
    def __init__(self, model: Optional[str] = None):
        super().__init__(model or os.getenv("LLAMACPP_MODEL", "local-model"))
        self.api_url = os.getenv("LLAMACPP_URL", "http://localhost:8080/v1/chat/completions")

    def generate(self, prompt: str, system_instruction: Optional[str] = None, json_format: bool = False) -> str:
        payload = {
            "messages": [
                {"role": "system", "content": system_instruction or "You are a helpful assistant."},
                {"role": "user", "content": prompt}
            ]
        }
        try:
            if not EgressFilter.is_url_allowed(self.api_url):
                return f"Security Error: Blocked attempt to access non-allowlisted host in llama.cpp URL: {self.api_url}"
                
            response = requests.post(self.api_url, json=payload, timeout=120)
            data = response.json()
            return data.get("choices", [{}])[0].get("message", {}).get("content", "")
        except Exception as e:
            return f"llama.cpp Error: {e}"

class AnthropicClient(LLMClient):
    """Client for Anthropic Claude models via official SDK."""
    def __init__(self, model: Optional[str] = None):
        super().__init__(model or os.getenv("ANTHROPIC_MODEL", "claude-3-5-sonnet-20240620"))
        self.api_key = os.getenv("ANTHROPIC_API_KEY")

    def generate(self, prompt: str, system_instruction: Optional[str] = None, json_format: bool = False) -> str:
        try:
            EgressFilter.validate_request("https://api.anthropic.com")
            import anthropic
            client = anthropic.Anthropic(api_key=self.api_key)
            
            messages = [{"role": "user", "content": prompt}]
            kwargs = {
                "model": self.model,
                "max_tokens": 4096,
                "messages": messages,
            }
            if system_instruction:
                kwargs["system"] = system_instruction
            
            response = client.messages.create(**kwargs)
            return response.content[0].text
        except Exception as e:
            return f"Anthropic Error: {e}"
