import os
import json
from typing import Dict, Any, Optional
from inference.llm_client import LLMClient
from inference.inference_manager import InferenceManager

class SchemaDesigner:
    """
    Designs and evolves the app.exegol.json manifest for Exegol-compatible applications.
    Ensures adherence to the standardized schema.
    """

    SYSTEM_PROMPT = """
    You are the Lead Schema Designer at Exegol. Your goal is to create or update an 'app.exegol.json' 
    manifest that accurately describes an application's requirements, architecture, and deployment 
    metadata.
    
    Standard Schema Keys:
    - app_name: (String)
    - version: (SemVer string)
    - architecture: { diagram_type: "mermaid", source: "README.md" | "inline" }
    - inference: { provider: "ollama" | "gemini", base_model: string }
    - components: List of { name: string, role: string, type: "service" | "agent" | "ui" }
    
    Output ONLY the valid JSON content for the 'app.exegol.json' file.
    """

    @classmethod
    def design_schema(cls, app_description: str, client: Optional[LLMClient] = None) -> Dict[str, Any]:
        """
        Generates a new app.exegol.json based on a description.
        """
        if client is None:
            client = InferenceManager.get_client()

        prompt = f"Design an app.exegol.json manifest for the following app: {app_description}"
        
        response = client.generate(prompt, system_instruction=cls.SYSTEM_PROMPT, json_format=True)
        return client.parse_json_response(response)

    @classmethod
    def save_schema(cls, repo_path: str, schema_data: Dict[str, Any]) -> str:
        """
        Saves the manifest to the repository root.
        """
        manifest_path = os.path.join(repo_path, "app.exegol.json")
        try:
            with open(manifest_path, 'w', encoding='utf-8') as f:
                json.dump(schema_data, f, indent=4)
            return f"Manifest saved to {manifest_path}"
        except Exception as e:
            return f"Error saving manifest: {e}"

if __name__ == "__main__":
    desc = "A real-time agentic chat application with a React frontend and a FastAPI backend using Gemini for inference."
    print(json.dumps(SchemaDesigner.design_schema(desc), indent=2))
