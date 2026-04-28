import os
import json
from typing import Optional

def introspect_agent(repo_path: str, agent_id: str, session_id: Optional[str] = None) -> str:
    """Provides a detailed breakdown of an agent's activities by auditing its logs and plans.
    
    If session_id is provided, focuses on that specific execution.
    Otherwise, reviews the most recent activity for the specified agent.
    """
    logs_dir = os.path.join(repo_path, ".exegol", "interaction_logs")
    if not os.path.exists(logs_dir):
        return f"Error: No logs directory found at {logs_dir}"

    relevant_logs = []
    
    # 1. Gather all relevant log files
    for filename in os.listdir(logs_dir):
        if not filename.endswith(".json"):
            continue
            
        filepath = os.path.join(logs_dir, filename)
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                data = json.load(f)
                
                # Filter by agent_id (handle both 'DeveloperDexAgent' and 'dex' style IDs)
                log_agent_id = data.get("agent_id", "").lower()
                target_agent_id = agent_id.lower().replace("_agent", "")
                
                if target_agent_id in log_agent_id or log_agent_id in target_agent_id:
                    if session_id:
                        if data.get("session_id") == session_id:
                            relevant_logs.append(data)
                    else:
                        relevant_logs.append(data)
        except:
            continue

    if not relevant_logs:
        return f"No interaction logs found for agent '{agent_id}'" + (f" and session '{session_id}'" if session_id else "")

    # Sort by timestamp descending
    relevant_logs.sort(key=lambda x: x.get("timestamp", ""), reverse=True)
    
    # 2. Build the introspection report
    target_logs = relevant_logs if session_id else relevant_logs[:5] # Last 5 runs if no session
    
    report = f"### Introspection Report: {agent_id}\n"
    if session_id:
        report += f"**Focus Session:** {session_id}\n\n"
    else:
        report += f"**Reviewing last {len(target_logs)} activities**\n\n"

    for log in target_logs:
        ts = log.get("timestamp", "Unknown Time")
        sid = log.get("session_id", "Unknown Session")
        outcome = log.get("outcome", "unknown").upper()
        summary = log.get("task_summary", "No summary provided.")
        
        report += f"#### [{ts}] Session: {sid}\n"
        report += f"- **Outcome:** {outcome}\n"
        report += f"- **Steps Used:** {log.get('steps_used', 'N/A')}\n"
        report += f"- **Duration:** {log.get('duration_seconds', 'N/A')}s\n"
        report += f"- **Summary:** {summary}\n"
        
        if log.get("errors"):
            report += f"- **Errors:** {', '.join(log['errors'])}\n"
            
        # 3. Look for related implementation plans (Dex specific)
        if "dex" in agent_id.lower():
            # Extract date for plan matching (e.g. 20260427)
            date_str = ts.split('T')[0].replace('-', '')
            for filename in os.listdir(logs_dir):
                if filename.startswith("plan_dex") and date_str in filename and filename.endswith(".md"):
                    report += f"- **Related Plan Found:** `{filename}`\n"
        
        report += "\n---\n"

    return report
