import os
import re


class MarkdownMaceAgent:
    """Specializes in formatting and optimizing markdown files across the repository."""

    def __init__(self, llm_client):
        self.llm_client = llm_client
        self.name = "MarkdownMaceAgent"
        self.max_steps = 5
        self.tools = ["markdown_formatter", "file_namer"]
        self.success_metrics = {
            "markdown_lint_errors": {
                "description": "Number of lint errors in generated markdown output",
                "target": "0",
                "current": None
            },
            "doc_formatting_consistency": {
                "description": "Percentage of generated docs following the standard template",
                "target": "100%",
                "current": None
            }
        }
        self.system_prompt = self.llm_client.generate_system_prompt(self)

    def _generate_filename(self, text: str) -> str:
        # Take the first 5 words to create a basic slug
        words = text.split()[:5]
        slug = "_".join(words).lower()
        # Remove non-alphanumeric characters
        slug = re.sub(r'[^a-z0-9_]', '', slug)
        if not slug:
            slug = "markdown_output"
        return f"{slug}.md"

    def execute(self, handoff):
        """Execute with a clean HandoffContext — no prior session memory required.

        Reads raw text from .exegol/pending_format.txt if available.
        """
        repo_path = handoff.repo_path
        print(f"[{self.name}] Session {handoff.session_id} — waking up to process text into markdown...")

        # Read input from filesystem instead of a method parameter
        pending_file = os.path.join(repo_path, ".exegol", "pending_format.txt")
        if os.path.exists(pending_file):
            with open(pending_file, 'r', encoding='utf-8') as f:
                input_text = f.read()
        else:
            input_text = "No pending content to format."

        filename = self._generate_filename(input_text)

        # Here would go the complex logic to use an LLM or similar
        # to format the input_text into proper Markdown structure.
        # For now, we perform a basic placeholder structuring.
        markdown_content = f"# Generated Document\n\n{input_text}\n"

        print(f"[{self.name}] Generated file name: {filename}")
        print(f"[{self.name}] Formatted content into markdown.")

        return {
            "status": "Success",
            "filename": filename,
            "content": markdown_content
        }
