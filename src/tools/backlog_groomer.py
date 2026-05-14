import os
from typing import List, Dict, Any, Optional
from tools.backlog_manager import BacklogManager

def groom_backlog(repo_path: str) -> Dict[str, Any]:
    """Standardized tool to select and prioritize the next task from the backlog.
    
    Returns:
        Dict: {
            "task": Dict | None,
            "source": str,
            "summary": str
        }
    """
    bm = BacklogManager(repo_path)
    backlog = bm.load_backlog()
    
    selected_task = None
    source = "none"

    # 1. Backlog 'todo' or 'backlogged' (Prioritize High/Critical)
    for t in backlog:
        if t.get("status") in ["todo", "backlogged", "pending_prioritization"]:
            if t.get("priority") in ["critical", "high"]:
                selected_task = t
                source = "backlog"
                break

    # 2. Fallback to any other 'todo' backlog items
    if not selected_task:
        for t in backlog:
            if t.get("status") in ["todo", "backlogged", "pending_prioritization"]:
                selected_task = t
                source = "backlog"
                break

    if selected_task:
        # Automatically update status to 'in_progress' to prevent race conditions
        bm.update_task_status(selected_task.get("id"), "in_progress")
        summary = f"Selected task {selected_task.get('id')} from {source}: {selected_task.get('summary')}"
    else:
        summary = "No actionable tasks found in backlog."

    return {
        "task": selected_task,
        "source": source,
        "summary": summary
    }
