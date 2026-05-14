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
    os.environ["EXEGOL_ACTIVE_AGENT"] = agent_name
    
    # 1. Research (Optional but recommended for agentic feel)
    search_query = f"best practices and implementation for: {task_description[:200]}"
    research_results = web_search(search_query, num_results=2)
    
    # 2. Plan
    files_in_repo = os.listdir(repo_path)
    # Filter out hidden/non-source files if needed, but for now just list top level
    
    planning_prompt = f"""You are the 'Agentic Coding' engine. Your ONLY output must be a valid JSON array — no explanations, no markdown, no prose.

Task to implement:
{task_description}

Implementation Research: {json.dumps(research_results)}

Existing Files (Top Level): {files_in_repo}

Return a JSON array of file action objects. Each object MUST have these EXACT keys:
{{
    "type": "write" | "replace" | "regex",
    "path": "relative/path/to/file",
    "content": "<new content or replacement string>",
    "target": "<text to replace or regex pattern>" (required only for replace/regex types),
    "reason": "<one-line rationale>"
}}

Example output format:
[
  {{"type": "write", "path": "scratch/notes.txt", "content": "hello", "reason": "Create notes file"}}
]

Respond with ONLY the JSON array. No other text."""
    
    try:
        response = llm_client.generate(planning_prompt, system_instruction=system_prompt, json_format=True)
        actions = llm_client.parse_json_response(response)
    except Exception as e:
        return f"Error during planning: {str(e)}"
        
    if not actions or not isinstance(actions, list):
        # Save raw failed response for debugging
        try:
            with open(os.path.join(repo_path, "scratch", "failed_plan_response.txt"), "w", encoding="utf-8") as f:
                f.write(f"ATTEMPT 1:\n{response}\n")
        except: pass

        # Handle if LLM returns a dict with "actions" key
        if isinstance(actions, dict) and "actions" in actions:
            actions = actions["actions"]
        else:
            # Retry once with an even stricter prompt before giving up
            print(f"[AgenticCoding] Parse failed on first attempt — retrying with strict JSON prompt.")
            retry_prompt = (
                f"Return ONLY a valid JSON array (no markdown, no prose) of file actions for this task:\n"
                f"{task_description}\n\n"
                f"Example: [{{\"type\": \"write\", \"path\": \"scratch/out.txt\", \"content\": \"hello\", \"reason\": \"demo\"}}]"
            )
            try:
                response2 = llm_client.generate(retry_prompt, system_instruction=system_prompt, json_format=True)
                actions = llm_client.parse_json_response(response2)
                
                # Save raw retry response
                try:
                    with open(os.path.join(repo_path, "scratch", "failed_plan_response.txt"), "a", encoding="utf-8") as f:
                        f.write(f"\nATTEMPT 2 (Retry):\n{response2}\n")
                except: pass

                if isinstance(actions, dict) and "actions" in actions:
                    actions = actions["actions"]
                
                if not isinstance(actions, list):
                    # Final Hail Mary: simple regex extraction for anything that looks like a JSON array
                    import re
                    match = re.search(r'\[\s*\{.*\}\s*\]', response2, re.DOTALL)
                    if match:
                        try:
                            actions = json.loads(match.group(0))
                            print(f"[AgenticCoding] Hail Mary: Extracted JSON array via regex.")
                        except: pass
                
                if not isinstance(actions, list):
                    return "Failed to parse coding plan from LLM after retry. See scratch/failed_plan_response.txt"
            except Exception as e2:
                return f"Error during planning retry: {str(e2)}"

    results = []
    steps_used = 0
    
    print(f"[AgenticCoding] Parsed {len(actions)} actions to execute.")
    
    for action in actions:
        if steps_used >= max_steps:
            results.append("Reached max_steps limit.")
            break
            
        action_type = action.get("type")
        # Handle variations in model output keys
        path = action.get("path") or action.get("file") or action.get("filename")
        content = action.get("content") or action.get("text") or action.get("code")
        target = action.get("target") or action.get("pattern") or ""
        reason = action.get("reason", "Applying agentic coding update")
        
        if not path or content is None:
            print(f"[AgenticCoding] Skipping invalid action: {action}")
            continue
            
        # Pulse heartbeat to signal progress (arch_agent_heartbeat)
        from tools.heartbeat_monitor import HeartbeatMonitor
        HeartbeatMonitor.pulse_session(repo_path, session_id)
            
        file_path = os.path.join(repo_path, path)
        
        try:
            if action_type == "write":
                res = write_file(file_path, content, reason=reason)
                results.append(f"Write {path}: {res}")
                outcome = "failure" if res.startswith("Error:") else "success"
            elif action_type == "replace":
                res = replace_content(file_path, target, content, reason=reason)
                results.append(f"Replace in {path}: {res}")
                outcome = "failure" if res.startswith("Error:") else "success"
            elif action_type == "regex":
                res = search_replace_regex(file_path, target, content, reason=reason)
                results.append(f"Regex in {path}: {res}")
                outcome = "failure" if res.startswith("Error:") else "success"
            else:
                results.append(f"Unknown action type: {action_type}")
                continue
                
            steps_used += 1
            
            if outcome == "failure":
                raise Exception(res)
            
            # Log individual interaction (arch_dex_granular_logging)
            log_interaction(
                agent_id=agent_name,
                outcome=outcome,
                task_summary=f"{action_type.capitalize()} {path}: {reason}",
                repo_path=repo_path,
                steps_used=1,
                session_id=session_id,
                state_changes={"file_modified": path}
            )

        except Exception as e:
            error_msg = str(e)
            results.append(f"Error executing action on {path}: {error_msg}")
            log_interaction(
                agent_id=agent_name,
                outcome="failure",
                task_summary=f"Failed {action_type} on {path}",
                repo_path=repo_path,
                steps_used=1,
                session_id=session_id,
                errors=[error_msg]
            )

    summary = f"Coding cycle complete for {agent_name}. Results:\n" + "\n".join(results)
    return {
        "summary": summary,
        "actions": actions,
        "results": results
    }
