import os
import re
from typing import Dict, Any, Optional

class ReadmeParser:
    """
    Parses README.md files to extract architectural metadata, 
    existing Mermaid diagrams, and feature lists.
    """

    @staticmethod
    def parse(repo_path: str) -> Dict[str, Any]:
        """
        Parses the README.md in the given repository path.
        """
        readme_path = os.path.join(repo_path, "README.md")
        if not os.path.exists(readme_path):
            return {"error": "README.md not found"}

        try:
            with open(readme_path, 'r', encoding='utf-8') as f:
                content = f.read()

            # 1. Extract Mermaid Diagrams
            mermaid_blocks = re.findall(r'```mermaid\s*(.*?)\s*```', content, re.DOTALL)
            
            # 2. Extract Main Heading
            title_match = re.search(r'^#\s+(.*)', content, re.MULTILINE)
            title = title_match.group(1).strip() if title_match else "Unknown Project"

            # 3. Extract Features (list items under a Features heading)
            features = []
            feature_section = re.search(r'#+\s+Features(.*?)(?=#+|$)', content, re.DOTALL | re.IGNORECASE)
            if feature_section:
                features = re.findall(r'-\s+(.*)', feature_section.group(1))

            # 4. Extract Architecture Description
            arch_section = re.search(r'#+\s+Architecture(.*?)(?=#+|$)', content, re.DOTALL | re.IGNORECASE)
            arch_desc = arch_section.group(1).strip() if arch_section else ""

            return {
                "title": title,
                "has_mermaid": len(mermaid_blocks) > 0,
                "mermaid_count": len(mermaid_blocks),
                "mermaid_diagrams": mermaid_blocks,
                "features": features,
                "architecture_description": arch_desc,
                "content_length": len(content)
            }
        except Exception as e:
            return {"error": f"Failed to parse README: {e}"}

if __name__ == "__main__":
    import json
    repo = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
    print(json.dumps(ReadmeParser.parse(repo), indent=2))
