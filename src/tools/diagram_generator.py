import os
import json
from typing import Optional
from inference.llm_client import LLMClient
from inference.inference_manager import InferenceManager

class DiagramGenerator:
    """
    Generates Mermaid architecture diagrams by analyzing the repository structure.
    Uses an LLM to interpret the relationships between components.
    """

    SYSTEM_PROMPT = """
    You are an Architecture Visualization Expert. Your goal is to generate a high-level Mermaid diagram 
    representing the software architecture of a given repository.
    
    Guidelines:
    1. Use 'graph TD' for the diagram.
    2. Focus on key components: entry points, core logic, tools, agents, and data storage.
    3. Group related components into subgraphs (e.g., 'Core', 'Agents', 'Tools').
    4. Keep the diagram concise and readable.
    5. Output ONLY the Mermaid code block starting with ```mermaid and ending with ```.
    """

    @classmethod
    def generate_diagram(cls, repo_path: str, client: Optional[LLMClient] = None) -> str:
        """
        Analyzes the repo and returns a Mermaid diagram string.
        """
        if client is None:
            client = InferenceManager.get_client()

        # Gather file structure (simplified)
        structure = []
        for root, dirs, files in os.walk(repo_path):
            # Skip hidden and env dirs
            dirs[:] = [d for d in dirs if not d.startswith('.') and d not in ('venv', '__pycache__', 'node_modules')]
            rel_root = os.path.relpath(root, repo_path)
            if rel_root == ".":
                structure.append(f"Root: {files}")
            else:
                # Limit depth or number of files to avoid prompt bloat
                if rel_root.count(os.sep) < 2:
                    structure.append(f"{rel_root}/: {files[:10]}")

        # Try to read the main README for context
        readme_context = ""
        readme_path = os.path.join(repo_path, "README.md")
        if os.path.exists(readme_path):
            with open(readme_path, 'r', encoding='utf-8') as f:
                readme_context = f.read()[:2000] # First 2k chars

        prompt = f"""
        Repository Path: {repo_path}
        
        File Structure:
        {json.dumps(structure, indent=2)}
        
        README Context:
        {readme_context}
        
        Generate a Mermaid diagram for this repository.
        """

        response = client.generate(prompt, system_instruction=cls.SYSTEM_PROMPT)
        
        # Extract mermaid block
        import re
        match = re.search(r'```mermaid\s*(.*?)\s*```', response, re.DOTALL)
        if match:
            return match.group(1).strip()
        
        return response.strip()

if __name__ == "__main__":
    # Test generation
    repo = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
    print(DiagramGenerator.generate_diagram(repo))
