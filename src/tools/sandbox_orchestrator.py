import os
import json
import shutil
import uuid
import datetime
from pathlib import Path
from typing import Dict, Optional, Any

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

def run_sandbox_command(sandbox_path: str, command: str, env: Optional[Dict[str, str]] = None) -> Dict[str, Any]:
    """
    Executes a command within the specified sandbox directory.
    - Handles environment variables.
    - Automatically uses the current python executable for 'python' or 'pip' commands.
    - Routes fatal errors to the fleet router.
    """
    import subprocess
    import sys
    
    path = Path(sandbox_path)
    if not path.exists():
        return {"error": f"Sandbox path {sandbox_path} does not exist.", "exit_code": -1}

    # Prepare environment
    full_env = os.environ.copy()
    
    # Load env from app.exegol.json if exists
    app_json_path = path / "app.exegol.json"
    if app_json_path.exists():
        try:
            with open(app_json_path, "r", encoding="utf-8") as f:
                app_data = json.load(f)
                config_env = app_data.get("env", {})
                if isinstance(config_env, dict):
                    full_env.update(config_env)
        except Exception as e:
            print(f"[SandboxOrchestrator] Warning: Failed to load app.exegol.json env: {e}")

    if env:
        full_env.update(env)
    
    # Add sandbox path to PYTHONPATH to ensure local modules are importable
    if "PYTHONPATH" in full_env:
        full_env["PYTHONPATH"] = f"{sandbox_path}{os.pathsep}{full_env['PYTHONPATH']}"
    else:
        full_env["PYTHONPATH"] = sandbox_path

    # Sanitize command: if it starts with 'python ' or 'pip ', use sys.executable
    if command.startswith("python "):
        command = f'"{sys.executable}" {command[7:]}'
    elif command.startswith("pip "):
        command = f'"{sys.executable}" -m pip {command[4:]}'

    print(f"[SandboxOrchestrator] Executing: {command} in {sandbox_path}")

    try:
        # Run the command with a timeout
        result = subprocess.run(
            command,
            cwd=str(path),
            shell=True,
            capture_output=True,
            text=True,
            env=full_env,
            timeout=60  # Increased timeout for complex sandbox tasks
        )
        
        # Always route terminal errors with 'FATAL' to the Exegol Fleet
        from tools.fatal_error_router import check_and_route_terminal_output
        is_fatal = check_and_route_terminal_output(sandbox_path, result.stdout, result.stderr, command)
        
        return {
            "stdout": result.stdout,
            "stderr": result.stderr,
            "exit_code": result.returncode,
            "is_fatal": is_fatal
        }
    except subprocess.TimeoutExpired as e:
        return {
            "error": "Command timed out",
            "stdout": e.stdout.decode() if e.stdout else "",
            "stderr": e.stderr.decode() if e.stderr else "",
            "exit_code": -1
        }
    except Exception as e:
        error_msg = str(e)
        if "FATAL" in error_msg.upper():
             from tools.fatal_error_router import route_fatal_error
             route_fatal_error(sandbox_path, error_msg)
        return {
            "error": error_msg,
            "exit_code": -1
        }

