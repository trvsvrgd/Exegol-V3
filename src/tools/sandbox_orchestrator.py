import os
import shutil
import uuid
import datetime
from pathlib import Path
from typing import Dict, Optional

def create_sandbox(repo_path: str, app_id: str) -> str:
    """
    Creates a unique sandbox directory for a given application ID.
    Returns the absolute path to the created sandbox.
    """
    exegol_dir = Path(repo_path) / ".exegol"
    sandboxes_dir = exegol_dir / "sandboxes"
    sandboxes_dir.mkdir(parents=True, exist_ok=True)
    
    unique_id = uuid.uuid4().hex[:8]
    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    sandbox_name = f"{app_id}_{timestamp}_{unique_id}"
    sandbox_path = sandboxes_dir / sandbox_name
    
    sandbox_path.mkdir(parents=True, exist_ok=True)
    
    # Initialize basic metadata
    metadata = {
        "app_id": app_id,
        "created_at": datetime.datetime.now().isoformat(),
        "status": "initialized"
    }
    
    # We could write this to a .sandbox_meta.json if needed
    
    return str(sandbox_path)

def deploy_to_sandbox(sandbox_path: str, file_map: Dict[str, str]):
    """
    Deploys files to a sandbox directory.
    file_map: { relative_path: content_string }
    """
    base_path = Path(sandbox_path)
    for rel_path, content in file_map.items():
        file_path = base_path / rel_path
        file_path.parent.mkdir(parents=True, exist_ok=True)
        with open(file_path, "w", encoding="utf-8") as f:
            f.write(content)

def cleanup_sandbox(sandbox_path: str):
    """
    Removes a sandbox directory.
    """
    path = Path(sandbox_path)
    if path.exists() and ".exegol/sandboxes" in str(path):
        shutil.rmtree(path)

def run_sandbox_command(sandbox_path: str, command: str) -> Dict[str, str]:
    """
    Executes a command within the specified sandbox directory.
    Returns a dictionary with 'stdout', 'stderr', and 'exit_code'.
    """
    import subprocess
    
    path = Path(sandbox_path)
    if not path.exists():
        return {"error": f"Sandbox path {sandbox_path} does not exist."}

    try:
        # Run the command with a timeout to prevent runaway processes
        result = subprocess.run(
            command,
            cwd=str(path),
            shell=True,
            capture_output=True,
            text=True,
            timeout=30  # 30 second timeout for sandbox commands
        )
        
        return {
            "stdout": result.stdout,
            "stderr": result.stderr,
            "exit_code": result.returncode
        }
    except subprocess.TimeoutExpired as e:
        return {
            "error": "Command timed out",
            "stdout": e.stdout.decode() if e.stdout else "",
            "stderr": e.stderr.decode() if e.stderr else "",
            "exit_code": -1
        }
    except Exception as e:
        return {
            "error": str(e),
            "exit_code": -1
        }

