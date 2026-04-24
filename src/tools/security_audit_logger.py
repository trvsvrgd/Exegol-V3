import os
import json
import datetime
import uuid
import tempfile
from typing import Optional, Dict, Any

def log_security_event(
    actor: str,
    action: str,
    outcome: str,
    repo_path: str,
    details: Optional[Dict[str, Any]] = None,
    session_id: Optional[str] = None
) -> str:
    """
    Logs a security-relevant event to a centralized, append-only (simulated via atomic rewrite) audit log.
    
    Fields:
        actor: The agent or user performing the action.
        action: The security-relevant operation (e.g., 'file_deletion', 'auth_failure').
        outcome: The result ('success', 'failure', 'blocked').
        repo_path: Root of the repository.
        details: Metadata about the event.
        session_id: The execution session identifier.
    """
    audit_log_dir = os.path.join(repo_path, ".exegol", "security")
    os.makedirs(audit_log_dir, exist_ok=True)
    audit_file = os.path.join(audit_log_dir, "security_audit_log.json")
    
    timestamp = datetime.datetime.now().isoformat()
    event_id = uuid.uuid4().hex
    
    event_data = {
        "event_id": event_id,
        "timestamp": timestamp,
        "actor": actor,
        "session_id": session_id or "N/A",
        "action": action,
        "outcome": outcome,
        "details": details or {}
    }
    
    # Load existing logs
    logs = []
    if os.path.exists(audit_file):
        try:
            with open(audit_file, "r", encoding="utf-8") as f:
                logs = json.load(f)
                if not isinstance(logs, list):
                    logs = []
        except (json.JSONDecodeError, IOError):
            logs = []
            
    # Append new event
    logs.append(event_data)
    
    # Atomic write
    dir_name = os.path.dirname(os.path.abspath(audit_file))
    with tempfile.NamedTemporaryFile("w", dir=dir_name, suffix=".tmp", delete=False, encoding="utf-8") as tmp:
        json.dump(logs, tmp, indent=4)
        tmp_path = tmp.name
        
    try:
        os.replace(tmp_path, audit_file)
    except Exception as e:
        if os.path.exists(tmp_path):
            os.remove(tmp_path)
        print(f"[SecurityAuditLogger] Error writing to audit log: {e}")
        return ""
        
    return event_id
