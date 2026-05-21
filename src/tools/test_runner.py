import subprocess
import json
import os
import sys
from typing import Dict, Any
try:
    from tools.fatal_error_router import check_and_route_terminal_output
except ModuleNotFoundError:
    from src.tools.fatal_error_router import check_and_route_terminal_output


DEFAULT_TIMEOUT_SECONDS = int(os.environ.get("EXEGOL_PYTEST_TIMEOUT_SECONDS", "180"))


def _repo_local_basetemp(path: str) -> str:
    return os.path.join(os.path.abspath(path), ".pytest_tmp", "test_runner")


def run_tests(path: str, include_external: bool = False, timeout_seconds: int | None = None) -> Dict[str, Any]:
    """
    Executes pytest on the specified directory and returns structured results.

    By default this runs the deterministic local test scope only. External tests
    require network, providers, Docker, or other machine-local services and must
    be requested explicitly.
    """
    if not os.path.exists(path):
        return {"status": "error", "message": f"Path not found: {path}"}

    marker = "external" if include_external else "not external"
    basetemp = _repo_local_basetemp(path)
    os.makedirs(os.path.join(basetemp, "tmp"), exist_ok=True)
    timeout_seconds = timeout_seconds or DEFAULT_TIMEOUT_SECONDS

    print(f"[test_runner] Running pytest on {path}...")
    try:
        command_args = [
            sys.executable,
            "-m",
            "pytest",
            ".",
            "-v",
            "--tb=short",
            "-p",
            "no:cacheprovider",
            "-m",
            marker,
            "--basetemp",
            basetemp,
        ]
        command = subprocess.list2cmdline(command_args)
        env = os.environ.copy()
        env.setdefault("EXEGOL_DISABLE_SCHEDULER_FOR_TESTS", "1")
        env["TMP"] = os.path.join(basetemp, "tmp")
        env["TEMP"] = os.path.join(basetemp, "tmp")
        env["TMPDIR"] = os.path.join(basetemp, "tmp")

        result = subprocess.run(
            command_args,
            cwd=path,
            capture_output=True,
            text=True,
            timeout=timeout_seconds,
            env=env,
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
    except subprocess.TimeoutExpired as exc:
        return {
            "status": "error",
            "message": f"Tests timed out after {timeout_seconds} seconds",
            "stdout": exc.stdout or "",
            "stderr": exc.stderr or "",
        }
    except Exception as e:
        error_msg = f"Execution error: {str(e)}"
        if "FATAL" in error_msg:
             try:
                 from tools.fatal_error_router import route_fatal_error
             except ModuleNotFoundError:
                 from src.tools.fatal_error_router import route_fatal_error
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
