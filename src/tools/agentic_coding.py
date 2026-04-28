import os
import json
import time
from typing import List, Dict, Any, Optional
from tools.file_editor_tool import read_file, write_file, replace_content, search_replace_regex
from tools.web_search import web_search
from tools.fleet_logger import log_interaction

def execute_coding_task(
    task_description: str,
    repo_path: str,
    llm_client: Any,
    agent_name: str,
    system_prompt: str,
    max_steps: int = 10,
    session_id: str = "unknown"
) -> str:
    """
    A high-level tool that performs agentic coding: researches, plans, and executes file changes.
    
    Args:
        task_description: The description of the coding task to perform.
        repo_path: The root path of the repository.
        llm_client: The LLM client to use for planning.
        agent_name: The name of the agent calling this tool.
        system_prompt: The system prompt for the LLM.
        max_steps: Maximum number of file operations to perform.
        session_id: Current session ID for logging.
        
    Returns:
        A summary of the actions performed.
    """
    print(f"[AgenticCoding] Starting task for {agent_name}: {task_description[:100]}...")
    
    # 1. Research (Optional but recommended for agentic feel)
    search_query = f"best practices and implementation for: {task_description[:200]}"
    research_results = web_search(search_query, num_results=2)
    
    # 2. Plan
    files_in_repo = os.listdir(repo_path)
    # Filter out hidden/non-source files if needed, but for now just list top level
    
    planning_prompt = f"""
    You are the 'Agentic Coding' engine. Your goal is to implement the following task:
    Task: {task_description}
    
    Implementation Research: {json.dumps(research_results)}
    
    Existing Files (Top Level): {files_in_repo}
    
    Plan the necessary file modifications. Return a JSON list of actions.
    Each action should be:
    {{
        "type": "write" | "replace" | "regex",
        "path": "relative/path/to/file",
        "content": "new content" | "text to insert" | "replacement string",
        "target": "text to replace" | "regex pattern" (only for type: replace/regex),
        "reason": "Why this change is being made"
    }}
    """
    
    try:
        response = llm_client.generate(planning_prompt, system_instruction=system_prompt, json_format=True)
        actions = llm_client.parse_json_response(response)
    except Exception as e:
        return f"Error during planning: {str(e)}"
        
    if not actions or not isinstance(actions, list):
        # Handle if LLM returns a dict with "actions" key
        if isinstance(actions, dict) and "actions" in actions:
            actions = actions["actions"]
        else:
            return "Failed to parse coding plan from LLM."

    results = []
    steps_used = 0
    
    for action in actions:
        if steps_used >= max_steps:
            results.append("Reached max_steps limit.")
            break
            
        action_type = action.get("type")
        path = action.get("path")
        content = action.get("content")
        target = action.get("target", "")
        reason = action.get("reason", "Applying agentic coding update")
        
        if not path or content is None:
            continue
            
        file_path = os.path.join(repo_path, path)
        
        try:
            if action_type == "write":
                res = write_file(file_path, content, reason=reason)
                results.append(f"Write {path}: {res}")
            elif action_type == "replace":
                res = replace_content(file_path, target, content, reason=reason)
                results.append(f"Replace in {path}: {res}")
            elif action_type == "regex":
                res = search_replace_regex(file_path, target, content, reason=reason)
                results.append(f"Regex in {path}: {res}")
            else:
                results.append(f"Unknown action type: {action_type}")
                continue
                
            steps_used += 1
        except Exception as e:
            results.append(f"Error executing action on {path}: {str(e)}")

    summary = f"Coding cycle complete for {agent_name}. Results:\n" + "\n".join(results)
    return summary
