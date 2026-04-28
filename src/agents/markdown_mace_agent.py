import os
from tools.markdown_formatter import format_markdown
from tools.file_namer import generate_filename


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

    def execute(self, handoff):
        """Execute with a clean HandoffContext — no prior session memory required.

        Reads raw text from .exegol/pending_format.txt if available.
        """
        repo_path = handoff.repo_path
        print(f"[{self.name}] Session {handoff.session_id} — waking up to process text into markdown...")

        # Read input from filesystem
        pending_file = os.path.join(repo_path, ".exegol", "pending_format.txt")
        if os.path.exists(pending_file):
            with open(pending_file, 'r', encoding='utf-8') as f:
                input_text = f.read()
        else:
            input_text = "No pending content to format."

        # 1. Generate filename based on context
        filename = generate_filename(input_text)
        
        # 2. Format content using the tool
        # In a real scenario, we might use an LLM first to structure it,
        # then the formatter to clean it up.
        raw_markdown = f"# Generated Document\n\n{input_text}"
        markdown_content = format_markdown(raw_markdown)

        print(f"[{self.name}] Generated file name: {filename}")
        print(f"[{self.name}] Formatted content into markdown.")

        return {
            "status": "Success",
            "filename": filename,
            "content": markdown_content
        }
