import json
import os
from typing import Dict, Any

def generate_active_prompt(task: Dict[str, Any], repo_path: str, llm_client, system_prompt: str) -> Dict[str, Any]:
    """Standardized tool to context-enrich a task into a detailed developer instruction set.
    
    Args:
        task: The task object from the backlog.
        repo_path: Path to the target repository.
        llm_client: Client used for inference.
        system_prompt: The calling agent's system prompt.

    Returns:
        Dict: {
            "prompt": str,
            "success": bool,
            "error": str | None
        }
    """
    print(f"[PromptGenerator] Researching feasibility and context for: {task.get('summary')}")
    
    # 1. Research phase
    from tools.web_search import web_search
    search_query = f"technical implementation details and best practices for: {task.get('summary')}"
    research = web_search(search_query, num_results=2)
    
    # 2. Enrichment phase
    context_prompt = f"""
    Expand this task into a detailed developer instruction set.
    Task Summary: {task.get('summary')}
    Task Description: {task.get('description', 'N/A')}
    Repository: {repo_path}
    
    Implementation Research Context:
    {json.dumps(research, indent=2)}
    
    Your output should include:
    1. A clear implementation plan.
    2. Specific files to analyze or modify.
    3. Potential risks or technical debt to watch for.

    Format as Markdown.
    """
    
    try:
        response = llm_client.generate(context_prompt, system_instruction=system_prompt)
        full_prompt = f"# Active Developer Task\n\n**Task ID:** {task.get('id')}\n\n{response}"
        return {
            "prompt": full_prompt,
            "success": True,
            "error": None
        }
    except Exception as e:
        error_msg = f"Failed to generate prompt: {str(e)}"
        print(f"[PromptGenerator] {error_msg}")
        # Fallback to a simple prompt
        fallback_prompt = f"# Active Developer Task\n\n**Task ID:** {task.get('id')}\n\n## Instructions\n{task.get('summary')}\n"
        return {
            "prompt": fallback_prompt,
            "success": False,
            "error": error_msg
        }
