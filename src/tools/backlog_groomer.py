import os
from typing import List, Dict, Any, Optional
from tools.backlog_manager import BacklogManager

ACTIONABLE_STATUSES = {"todo", "backlogged", "pending_prioritization"}


def _is_actionable(task: Dict[str, Any]) -> bool:
    return task.get("status") in ACTIONABLE_STATUSES


def _is_failure_recovery(task: Dict[str, Any]) -> bool:
    task_id = str(task.get("id") or "")
    return task_id.startswith("auto_fail_") or task.get("blocker_type") == "agent_crash"


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

    # 1. Crash recovery should preempt normal feature work.
    for t in backlog:
        if _is_actionable(t) and _is_failure_recovery(t):
            selected_task = t
            source = "failure_recovery"
            break

    # 2. Backlog 'todo' or 'backlogged' (Prioritize High/Critical)
    for t in backlog:
        if selected_task:
            break
        if _is_actionable(t):
            if t.get("priority") in ["critical", "high"]:
                selected_task = t
                source = "backlog"
                break

    # 3. Fallback to any other 'todo' backlog items
    if not selected_task:
        for t in backlog:
            if _is_actionable(t):
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
