import os
import httpx
import asyncio
import traceback
from typing import Optional

def route_fatal_error(repo_path: str, error_message: str, context: Optional[str] = None):
    """
    Routes a fatal error to the Exegol Fleet API.
    This can be called synchronously from any tool.
    """
    api_url = os.getenv("EXEGOL_API_URL", "http://localhost:8000")
    api_key = os.getenv("EXEGOL_API_KEY", "dev-local-key")
    
    payload = {
        "repo_path": repo_path,
        "error_message": error_message,
        "context": context or traceback.format_exc()
    }
    
    print(f"[FatalErrorRouter] Routing fatal error to fleet: {error_message[:100]}...")
    
    try:
        # Using a synchronous approach for simplicity in existing tools
        with httpx.Client(timeout=10.0) as client:
            response = client.post(
                f"{api_url}/fatal-error",
                json=payload,
                headers={"X-API-Key": api_key}
            )
            response.raise_for_status()
            result = response.json()
            print(f"[FatalErrorRouter] Successfully routed. Task ID: {result.get('task_id')}")
            return result
    except Exception as e:
        print(f"[FatalErrorRouter] Failed to route fatal error: {e}")
        return None

def check_and_route_terminal_output(repo_path: str, stdout: str, stderr: str, command: str):
    """
    Checks terminal output for 'FATAL' and routes if found.
    """
    combined_output = f"{stdout}\n{stderr}"
    if "FATAL" in combined_output:
        context = f"Command: {command}\n\nSTDOUT:\n{stdout}\n\nSTDERR:\n{stderr}"
        # Extract the line containing FATAL
        fatal_lines = [line for line in combined_output.splitlines() if "FATAL" in line]
        error_msg = fatal_lines[0] if fatal_lines else "Terminal error with FATAL status"
        
        route_fatal_error(repo_path, error_msg, context)
        return True
    return False
