import os
import json
from typing import List, Dict, Any, Optional

def read_logs(repo_path: Optional[str] = None, limit: int = 50) -> List[Dict[str, Any]]:
    """Reads interaction logs from the repo or the global logs directory.
    
    Returns a list of session result dictionaries, sorted by timestamp descending.
    """
    log_paths = []
    
    # 1. Check repo-specific logs
    if repo_path:
        repo_logs_dir = os.path.join(repo_path, ".exegol", "interaction_logs")
        if os.path.isdir(repo_logs_dir):
            log_paths.append(repo_logs_dir)
            
    # 2. Check global logs directory
    global_logs_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "logs")
    if os.path.isdir(global_logs_dir):
        log_paths.append(global_logs_dir)

    if not log_paths:
        return []

    all_logs = []
    try:
        for logs_dir in log_paths:
            filenames = os.listdir(logs_dir)
            for filename in filenames:
                if filename.endswith(".json"):
                    file_path = os.path.join(logs_dir, filename)
                try:
                    with open(file_path, "r", encoding="utf-8") as f:
                        log_data = json.load(f)
                        if isinstance(log_data, dict):
                            all_logs.append(log_data)
                except (json.JSONDecodeError, IOError):
                    continue
        
        # Sort by timestamp (ISO 8601 string) descending
        all_logs.sort(key=lambda x: x.get("timestamp", ""), reverse=True)
        return all_logs[:limit]
    except Exception as e:
        print(f"[interaction_log_reader] Error: {e}")
        return []

def summarize_logs(logs: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Computes aggregate fleet metrics from a list of logs."""
    total = len(logs)
    if total == 0:
        return {
            "total_sessions": 0,
            "success_rate": 0,
            "avg_duration_seconds": 0,
            "unique_agents": [],
            "common_errors": []
        }

    successes = sum(1 for log in logs if log.get("outcome") == "success")
    durations = [log.get("duration_seconds", 0) for log in logs]
    
    agents = set()
    errors = []
    for log in logs:
        if log.get("agent_id"):
            agents.add(log["agent_id"])
        if log.get("errors"):
            errors.extend(log["errors"])

    # Basic error frequency
    error_counts = {}
    for err in errors:
        error_counts[err] = error_counts.get(err, 0) + 1
    sorted_errors = sorted(error_counts.items(), key=lambda x: x[1], reverse=True)

    return {
        "total_sessions": total,
        "success_count": successes,
        "failure_count": total - successes,
        "success_rate": f"{(successes / total) * 100:.1f}%",
        "avg_duration_seconds": round(sum(durations) / total, 2),
        "unique_agents": list(agents),
        "top_errors": [e[0] for e in sorted_errors[:5]]
    }

def get_agent_performance(agent_id: str, repo_path: Optional[str] = None) -> Dict[str, Any]:
    """Retrieves performance metrics for a specific agent across the fleet."""
    logs = read_logs(repo_path, limit=500)
    agent_logs = [l for l in logs if l.get("agent_id") == agent_id]
    return summarize_logs(agent_logs)

def get_recent_failures(limit: int = 5) -> List[Dict[str, Any]]:
    """Returns the most recent failed sessions for audit."""
    logs = read_logs(limit=200)
    failures = [l for l in logs if l.get("outcome") != "success"]
    return failures[:limit]
