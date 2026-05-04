import os
import time
from tools.markdown_formatter import format_markdown
from tools.file_namer import generate_filename
from tools.fleet_logger import log_interaction


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
        start_time = time.time()
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
        
        # 2. Use LLM to intelligently structure the content
        structuring_prompt = (
            "You are a professional technical writer. Convert the following raw text into a "
            "well-structured Markdown document. Use appropriate headers, bold text for emphasis, "
            "bullet points for lists, and tables for data where they add clarity. "
            "Output ONLY the markdown content, no preamble.\n\n"
            f"RAW TEXT:\n{input_text}"
        )
        
        print(f"[{self.name}] Analyzing content structure via LLM...")
        raw_markdown = self.llm_client.generate(structuring_prompt)
        
        # 3. Format/Lint the generated markdown
        markdown_content = format_markdown(raw_markdown)

        print(f"[{self.name}] Generated file name: {filename}")
        print(f"[{self.name}] Formatted content into markdown.")

        summary_msg = f"Markdown processing complete. Formatted content for {filename}."
        
        duration = time.time() - start_time
        log_interaction(
            agent_id=self.name,
            outcome="success",
            task_summary=summary_msg,
            repo_path=repo_path,
            duration_seconds=duration,
            session_id=handoff.session_id,
            state_changes={"filename": filename}
        )

        return {
            "status": "Success",
            "filename": filename,
            "content": markdown_content
        }
