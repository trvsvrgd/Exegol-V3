import os
import json
import re
import time
from typing import List, Dict, Any, Optional
from tools.file_editor_tool import read_file, write_file, replace_content, search_replace_regex
from tools.web_search import web_search
from tools.fleet_logger import log_interaction

# Session-scoped failure injection tracker — prevents backlog spam.
# Key: (session_id, error_type)  →  True if a backlog item was already injected.
_session_failure_injected: Dict[tuple, bool] = {}

# --- JSON Extraction Strategies (arch_dex_llm_parse_resilience) ---

def _strip_markdown_fences(text: str) -> str:
    """Removes ```json ... ``` or ``` ... ``` fences from LLM output."""
    # Strip ```json ... ``` or ``` ... ``` blocks
    stripped = re.sub(r"```(?:json)?\s*", "", text, flags=re.IGNORECASE)
    stripped = stripped.replace("```", "")
    return stripped.strip()


def _extract_json_array(text: str) -> Optional[list]:
    """
    Multi-strategy extractor: tries to pull a JSON array out of an LLM response
    using increasingly aggressive methods.
    
    Strategy order:
      1. Direct JSON parse (fastest path — works if LLM returned clean JSON)
      2. Strip markdown fences, then parse
      3. Regex-find the outermost [...] block and parse
      4. Regex-find the outermost {...} block (dict with embedded array), unwrap
    """
    if not text:
        return None

    # Strategy 1: Direct parse
    try:
        result = json.loads(text)
        if isinstance(result, list):
            return result
        if isinstance(result, dict):
            # Unwrap common LLM dict wrappers
            for key in ("actions", "steps", "plan", "tasks"):
                if isinstance(result.get(key), list):
                    return result[key]
    except (json.JSONDecodeError, ValueError):
        pass

    # Strategy 2: Strip markdown fences, then parse
    cleaned = _strip_markdown_fences(text)
    try:
        result = json.loads(cleaned)
        if isinstance(result, list):
            return result
        if isinstance(result, dict):
            for key in ("actions", "steps", "plan", "tasks"):
                if isinstance(result.get(key), list):
                    return result[key]
    except (json.JSONDecodeError, ValueError):
        pass

    # Strategy 3: Extract the first top-level [...] array via regex
    match = re.search(r"(\[[\s\S]*\])", cleaned)
    if match:
        try:
            result = json.loads(match.group(1))
            if isinstance(result, list):
                return result
        except (json.JSONDecodeError, ValueError):
            pass

    # Strategy 4: Extract the first top-level {...} dict and unwrap
    match = re.search(r"(\{[\s\S]*\})", cleaned)
    if match:
        try:
            result = json.loads(match.group(1))
            if isinstance(result, dict):
                for key in ("actions", "steps", "plan", "tasks"):
                    if isinstance(result.get(key), list):
                        return result[key]
        except (json.JSONDecodeError, ValueError):
            pass

    return None


def _validate_plan(actions: list) -> list:
    """
    Validates and normalises each action object against the required schema.
    
    Required keys: type, path, content
    Optional keys: target (for replace/regex), reason
    
    Returns a filtered list of valid actions, logging warnings for skipped ones.
    """
    REQUIRED_KEYS = {"type", "path", "content"}
    VALID_TYPES = {"write", "replace", "regex"}
    valid = []

    for i, action in enumerate(actions):
        if not isinstance(action, dict):
            print(f"[AgenticCoding][Validate] Action #{i} is not a dict — skipping: {action!r}")
            continue

        # Normalise key aliases before validation
        action.setdefault("path", action.pop("file", action.pop("filename", None)))
        action.setdefault("content", action.pop("text", action.pop("code", None)))
        action.setdefault("target", action.pop("pattern", ""))
        action.setdefault("reason", "Applying agentic coding update")

        missing = REQUIRED_KEYS - set(k for k, v in action.items() if v is not None)
        if missing:
            print(f"[AgenticCoding][Validate] Action #{i} missing keys {missing} — skipping: {action!r}")
            continue

        if action.get("type") not in VALID_TYPES:
            print(f"[AgenticCoding][Validate] Action #{i} has unknown type '{action.get('type')}' — skipping.")
            continue

        if action.get("type") in ("replace", "regex") and not action.get("target"):
            print(f"[AgenticCoding][Validate] Action #{i} type '{action['type']}' requires 'target' — skipping.")
            continue

        valid.append(action)

    return valid


def _inject_parse_failure_backlog(repo_path: str, session_id: str, error_type: str, detail: str):
    """
    Injects a single backlog task for a parse failure within this session.
    Deduplicates: only one item per (session_id, error_type) is ever injected.
    """
    key = (session_id, error_type)
    if _session_failure_injected.get(key):
        print(f"[AgenticCoding] Dedup: Skipping duplicate backlog injection for session '{session_id}', error '{error_type}'.")
        return

    _session_failure_injected[key] = True

    try:
        from tools.backlog_manager import BacklogManager
        import datetime
        bm = BacklogManager(repo_path)
        task_id = f"dex_parse_fail_{session_id[:8]}_{error_type[:20]}"
        bm.add_task({
            "id": task_id,
            "summary": f"DeveloperDex parse failure: {error_type} in session {session_id[:8]}",
            "priority": "high",
            "type": "bug",
            "status": "todo",
            "source_agent": "AgenticCoding",
            "rationale": f"LLM returned unparseable coding plan (error_type={error_type}). Detail: {detail[:500]}. Session: {session_id}.",
            "created_at": datetime.datetime.now().isoformat()
        })
    except Exception as e:
        print(f"[AgenticCoding] Failed to inject failure backlog item: {e}")


def execute_coding_task(
    task_description: str,
    repo_path: str,
    llm_client: Any,
    agent_name: str,
    system_prompt: str,
    max_steps: int = 10,
    session_id: str = "unknown"
) -> dict:
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
        A dict with keys: "summary" (str), "actions" (list), "results" (list).
    """
    print(f"[AgenticCoding] Starting task for {agent_name}: {task_description[:100]}...")
    os.environ["EXEGOL_ACTIVE_AGENT"] = agent_name

    # 1. Research (Optional but recommended for agentic feel)
    search_query = f"best practices and implementation for: {task_description[:200]}"
    research_results = web_search(search_query, num_results=2)

    # 2. Plan
    files_in_repo = os.listdir(repo_path)

    planning_prompt = f"""You are the 'Agentic Coding' engine. Your ONLY output must be a valid JSON array — no explanations, no markdown, no prose.

Task to implement:
{task_description}

Implementation Research: {json.dumps(research_results)}

Existing Files (Top Level): {files_in_repo}

Return a JSON array of file action objects. Each object MUST have these EXACT keys:
- "type": one of "write", "replace", or "regex"
- "path": relative path to the file
- "content": the new content or replacement string
- "target": the text to replace or regex pattern (required only for replace/regex types)
- "reason": one-line rationale

Example output:
[
  {{"type": "write", "path": "scratch/notes.txt", "content": "hello", "reason": "Create notes file"}}
]

Respond with ONLY the JSON array. No markdown fences. No prose. No explanation."""

    actions = None
    raw_response = ""

    try:
        raw_response = llm_client.generate(planning_prompt, system_instruction=system_prompt, json_format=True)
        actions = _extract_json_array(raw_response)
    except Exception as e:
        return {
            "summary": f"Error during planning: {str(e)}",
            "actions": [],
            "results": []
        }

    # Retry once if extraction failed
    if actions is None:
        _save_failed_response(repo_path, raw_response, attempt=1)
        print(f"[AgenticCoding] Multi-strategy parse failed on attempt 1 — retrying with strict prompt.")

        retry_prompt = (
            f"Return ONLY a valid JSON array (no markdown, no prose, no fences) of file actions for this task:\n"
            f"{task_description}\n\n"
            f"Example: [{{\"type\": \"write\", \"path\": \"scratch/out.txt\", \"content\": \"hello\", \"reason\": \"demo\"}}]"
        )
        try:
            raw_response2 = llm_client.generate(retry_prompt, system_instruction=system_prompt, json_format=True)
            actions = _extract_json_array(raw_response2)
            _save_failed_response(repo_path, raw_response2, attempt=2)
        except Exception as e2:
            return {
                "summary": f"Error during planning retry: {str(e2)}",
                "actions": [],
                "results": []
            }

    if actions is None:
        msg = "Failed to parse coding plan from LLM after retry. See scratch/failed_plan_response.txt"
        _inject_parse_failure_backlog(repo_path, session_id, "parse_failure", raw_response[:300])
        return {"summary": msg, "actions": [], "results": []}

    # 3. Validate plan structure
    validated_actions = _validate_plan(actions)
    if not validated_actions:
        msg = "LLM returned a plan with 0 valid actions after schema validation."
        _inject_parse_failure_backlog(repo_path, session_id, "empty_valid_plan", str(actions)[:300])
        return {"summary": msg, "actions": actions, "results": []}

    results = []
    steps_used = 0

    print(f"[AgenticCoding] Parsed and validated {len(validated_actions)}/{len(actions)} actions.")

    for action in validated_actions:
        if steps_used >= max_steps:
            results.append("Reached max_steps limit.")
            break

        action_type = action.get("type")
        path = action.get("path")
        content = action.get("content")
        target = action.get("target", "")
        reason = action.get("reason", "Applying agentic coding update")

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
        "actions": validated_actions,
        "results": results
    }


def _save_failed_response(repo_path: str, response: str, attempt: int):
    """Saves a failed LLM response to scratch/ for debugging."""
    try:
        scratch_dir = os.path.join(repo_path, "scratch")
        os.makedirs(scratch_dir, exist_ok=True)
        path = os.path.join(scratch_dir, "failed_plan_response.txt")
        mode = "w" if attempt == 1 else "a"
        with open(path, mode, encoding="utf-8") as f:
            f.write(f"ATTEMPT {attempt}:\n{response}\n\n")
    except Exception:
        pass
