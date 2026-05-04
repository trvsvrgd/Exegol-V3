import os
import json
import datetime
import uuid
import time
from typing import List, Optional, Dict, Any

def log_interaction(
    agent_id: str,
    outcome: str,
    task_summary: str,
    repo_path: str,
    steps_used: int = 0,
    duration_seconds: float = 0.0,
    errors: Optional[List[str]] = None,
    session_id: Optional[str] = None,
    state_changes: Optional[Dict[str, Any]] = None,
    metrics: Optional[Dict[str, Any]] = None,
    token_usage: int = 0,
    prompt_count: int = 0
) -> str:
    """
    Logs an agent's interaction to the .exegol/interaction_logs directory in JSON format.
    Includes input validation and retry logic for robust logging.
    """
    # Input Validation
    agent_id = str(agent_id) if agent_id else "unknown"
    outcome = str(outcome).lower() if outcome else "unknown"
    if outcome not in ["success", "failure", "partial"]:
        outcome = "unknown"
    task_summary = str(task_summary) if task_summary else "No summary provided."
    steps_used = steps_used if isinstance(steps_used, int) else 0
    duration_seconds = duration_seconds if isinstance(duration_seconds, (float, int)) else 0.0
    
    interaction_logs_dir = os.path.join(repo_path, ".exegol", "interaction_logs")
    os.makedirs(interaction_logs_dir, exist_ok=True)
    
    timestamp = datetime.datetime.now().isoformat()
    ts_filename = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    unique_id = uuid.uuid4().hex[:6]
    
    log_data = {
        "timestamp": timestamp,
        "agent_id": agent_id,
        "session_id": session_id or unique_id,
        "outcome": outcome,
        "task_summary": task_summary,
        "steps_used": steps_used,
        "duration_seconds": round(duration_seconds, 2),
        "errors": errors or [],
        "state_changes": state_changes or {},
        "metrics": metrics or {},
        "token_usage": token_usage,
        "prompt_count": prompt_count,
        "repo_path": repo_path
    }
    
    filename = f"log_{agent_id}_{ts_filename}_{unique_id}.json"
    filepath = os.path.join(interaction_logs_dir, filename)
    
    max_retries = 3
    for attempt in range(max_retries):
        try:
            with open(filepath, "w", encoding="utf-8") as f:
                json.dump(log_data, f, indent=4)
            break
        except OSError as e:
            if attempt == max_retries - 1:
                print(f"Failed to write interaction log {filename}: {e}")
            else:
                time.sleep(0.5 * (attempt + 1))
    
    # --- UNIVERSAL SELF-HEALING: Auto-report failures to Backlog and Slack ---
    if outcome == "failure":
        try:
            from tools.backlog_manager import BacklogManager
            from tools.slack_tool import post_to_slack
            
            bm = BacklogManager(repo_path)
            error_id = f"auto_fail_{agent_id}_{int(time.time())}"
            error_str = "; ".join(errors) if errors else "Unknown error."
            
            fail_task = {
                "id": error_id,
                "summary": f"FIX: {agent_id} autonomous failure",
                "priority": "high",
                "type": "bug",
                "status": "todo",
                "source_agent": "FleetLogger",
                "rationale": f"System-detected failure. Summary: {task_summary}. Errors: {error_str}",
                "created_at": datetime.datetime.now().isoformat()
            }
            bm.add_task(fail_task)
            
            # Notify Slack
            msg = (
                f"💥 *Agent Failure*: `{agent_id}` reported a failure in `{os.path.basename(repo_path)}`.\n"
                f"*Summary*: {task_summary}\n"
                f"*Errors*: `{error_str}`\n"
                f"A bug report has been injected into the backlog."
            )
            post_to_slack(msg)
        except Exception as e:
            print(f"[FleetLogger] Failed to auto-report failure: {e}")
                
    return filepath

def read_interaction_logs(repo_paths: List[str], days: int = 7) -> List[dict]:
    """
    Safely reads interaction logs from the last N days across multiple repositories.
    Includes retry logic and skips malformed JSON without silent failures.
    """
    cutoff_date = datetime.datetime.now() - datetime.timedelta(days=days)
    entries = []

    for repo_path in repo_paths:
        logs_dir = os.path.join(repo_path, ".exegol", "interaction_logs")
        if not os.path.isdir(logs_dir):
            continue

        for filename in sorted(os.listdir(logs_dir)):
            if not filename.endswith(".json"):
                continue
            filepath = os.path.join(logs_dir, filename)
            
            # Retry logic for reading logs
            max_retries = 3
            for attempt in range(max_retries):
                try:
                    with open(filepath, "r", encoding="utf-8") as f:
                        data = json.load(f)
                        
                    # Handle both single log dictionaries and legacy lists of logs
                    records = data if isinstance(data, list) else [data]
                    
                    for record in records:
                        if not isinstance(record, dict):
                            continue
                        ts_str = record.get("timestamp", "")
                        try:
                            ts = datetime.datetime.fromisoformat(ts_str)
                            if ts >= cutoff_date:
                                record["_repo_path"] = repo_path
                                entries.append(record)
                        except ValueError:
                            # Skip entries with invalid timestamps
                            pass
                    break  # Break out of retry loop on success
                except json.JSONDecodeError as e:
                    print(f"[LogReader] Malformed JSON in {filename}: {e}. Skipping.")
                    break  # Don't retry parsing malformed JSON
                except OSError as e:
                    if attempt == max_retries - 1:
                        print(f"[LogReader] Failed to read {filename} after {max_retries} attempts: {e}")
                    else:
                        time.sleep(0.2 * (attempt + 1))

    return entries
