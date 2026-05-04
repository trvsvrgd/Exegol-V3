import json
import os
from typing import Dict, Any
from tools.web_search import web_search

def generate_active_prompt(task: Dict[str, Any], repo_path: str, llm_client, system_prompt: str) -> str:
    """Uses LLM to context-enrich the task summary into a detailed developer instruction set.
    
    Includes web research for feasibility and best practices.
    """
    print(f"[PromptGenerator] Researching feasibility for: {task.get('summary')}")
    search_query = f"technical implementation details and best practices for: {task.get('summary')}"
    research = web_search(search_query, num_results=2)
    
    context_prompt = f"""
    Expand this task into a detailed developer instruction set.
    Task Summary: {task.get('summary')}
    Task Description: {task.get('description', 'N/A')}
    Repository: {repo_path}
    
    Implementation Research: {json.dumps(research)}
    
    Include relevant files to check and a step-by-step implementation plan.
    """
    try:
        response = llm_client.generate(context_prompt, system_instruction=system_prompt)
        return f"# Active Developer Task\n\n**Task ID:** {task.get('id')}\n\n{response}"
    except Exception:
        # Fallback
        return f"# Active Developer Task\n\n**Task ID:** {task.get('id')}\n\n## Instructions\n{task.get('summary')}\n"
