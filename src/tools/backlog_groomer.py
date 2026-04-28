import json
from typing import List, Dict, Any, Tuple

def select_next_task(backlog: List[Dict[str, Any]]) -> Tuple[Dict[str, Any], str]:
    """Selects the next task to execute from the backlog based on priority and status.
    
    Logic:
    1. Prioritize 'todo', 'backlogged', or 'pending_prioritization' with 'critical' or 'high' priority.
    2. Fallback to any 'todo', 'backlogged', or 'pending_prioritization' items.
    """
    # 1. Backlog 'todo' or 'backlogged' (Prioritize High/Critical)
    for t in backlog:
        if t.get("status") in ["todo", "backlogged", "pending_prioritization"]:
            if t.get("priority") in ["critical", "high"]:
                return t, "backlog"

    # 2. Any other 'todo' backlog items
    for t in backlog:
        if t.get("status") in ["todo", "backlogged", "pending_prioritization"]:
            return t, "backlog"

    return None, None
