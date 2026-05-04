import subprocess
import json
import os
from typing import Dict, Any
from tools.fatal_error_router import check_and_route_terminal_output

def run_tests(path: str) -> Dict[str, Any]:
    """
    Executes pytest on the specified directory and returns structured results.
    """
    if not os.path.exists(path):
        return {"status": "error", "message": f"Path not found: {path}"}
    
    print(f"[test_runner] Running pytest on {path}...")
    try:
        # Run pytest and capture output
        command = f"python -m pytest {path} -v --tb=short"
        result = subprocess.run(
            ["python", "-m", "pytest", path, "-v", "--tb=short"],
            capture_output=True,
            text=True,
            timeout=60
        )
        
        # Always route terminal errors with 'FATAL' to the Exegol Fleet
        check_and_route_terminal_output(path, result.stdout, result.stderr, command)
        
        status = "pass" if result.returncode == 0 else "fail"
        
        return {
            "status": status,
            "exit_code": result.returncode,
            "stdout": result.stdout,
            "stderr": result.stderr,
            "message": "Tests completed" if status == "pass" else "Tests failed"
        }
    except subprocess.TimeoutExpired:
        return {"status": "error", "message": "Tests timed out after 60 seconds"}
    except Exception as e:
        error_msg = f"Execution error: {str(e)}"
        if "FATAL" in error_msg:
             from tools.fatal_error_router import route_fatal_error
             route_fatal_error(path, error_msg)
        return {"status": "error", "message": error_msg}

if __name__ == "__main__":
    # Test execution
    import sys
    target = sys.argv[1] if len(sys.argv) > 1 else os.getcwd()
    res = run_tests(target)
    print(f"Status: {res['status']}")
    if res['status'] == 'fail':
        print(res['stdout'])
