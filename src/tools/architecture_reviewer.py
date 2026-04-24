import os
import json
from typing import Dict, Any, Optional
from inference.llm_client import LLMClient
from inference.inference_manager import InferenceManager

class ArchitectureReviewer:
    """
    Performs a high-level architectural review of a repository.
    Analyzes file structure, dependencies, and core logic patterns.
    """

    SYSTEM_PROMPT = """
    You are the Senior Fleet Architect at Exegol. Your task is to perform a structural and architectural review 
    of a codebase to identify bottlenecks, anti-patterns, and scalability issues.
    
    Evaluate based on:
    1. **Modularity**: Are components decoupled and reusable?
    2. **Scalability**: Can the system handle increased load or complexity?
    3. **Resilience**: Are there circuit breakers, loop guards, and error handling?
    4. **Security**: Is there a clear trust boundary and RBAC?
    
    Provide your review in JSON format with:
    - score: (0-100)
    - findings: (List of issues)
    - recommendations: (List of concrete fixes)
    - status: (STABLE, DEGRADED, CRITICAL)
    """

    @classmethod
    def review(cls, repo_path: str, client: Optional[LLMClient] = None) -> Dict[str, Any]:
        """
        Reviews the repository and returns a structured report.
        """
        if client is None:
            client = InferenceManager.get_client()

        # Gather file structure
        structure = []
        for root, dirs, files in os.walk(repo_path):
            dirs[:] = [d for d in dirs if not d.startswith('.') and d not in ('venv', '__pycache__')]
            rel_root = os.path.relpath(root, repo_path)
            if rel_root.count(os.sep) < 2:
                structure.append(f"{rel_root}/: {files[:15]}")

        # Try to gather some core file contents (e.g., orchestrator, api, agents)
        core_context = ""
        core_files = [
            "src/orchestrator.py",
            "src/api.py",
            "src/handoff.py",
            "app.exegol.json"
        ]
        for cf in core_files:
            cf_path = os.path.join(repo_path, cf)
            if os.path.exists(cf_path):
                with open(cf_path, 'r', encoding='utf-8') as f:
                    core_context += f"\n--- {cf} ---\n{f.read()[:1000]}\n"

        prompt = f"""
        Reviewing Repository: {repo_path}
        
        File Structure:
        {json.dumps(structure, indent=2)}
        
        Core Logic Samples:
        {core_context}
        
        Provide an architectural review of this fleet repository.
        """

        response = client.generate(prompt, system_instruction=cls.SYSTEM_PROMPT, json_format=True)
        return client.parse_json_response(response)

if __name__ == "__main__":
    repo = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
    print(json.dumps(ArchitectureReviewer.review(repo), indent=2))
