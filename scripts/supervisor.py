import argparse
import os
import signal
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Dict, Optional

import requests


MAX_LOG_BYTES = 2_000_000


def rotate_log(path: Path) -> None:
    if not path.exists() or path.stat().st_size < MAX_LOG_BYTES:
        return
    stamp = datetime.now().strftime("%Y%m%d%H%M%S")
    path.replace(path.with_name(f"{path.stem}.{stamp}{path.suffix}"))


def probe(url: str, api_key: str = "") -> bool:
    headers = {"X-API-Key": api_key} if api_key else {}
    try:
        return requests.get(url, headers=headers, timeout=2).status_code < 500
    except requests.RequestException:
        return False


def start_process(name: str, command: list[str], cwd: Path, log_path: Path, env: Optional[dict] = None) -> subprocess.Popen:
    rotate_log(log_path)
    log_file = open(log_path, "a", encoding="utf-8", buffering=1)
    log_file.write(f"\n[{datetime.now().isoformat()}] starting {name}: {' '.join(command)}\n")
    return subprocess.Popen(command, cwd=str(cwd), stdout=log_file, stderr=subprocess.STDOUT, text=True, env=env)


def stop_process(proc: Optional[subprocess.Popen]) -> None:
    if not proc or proc.poll() is not None:
        return
    try:
        proc.terminate()
        proc.wait(timeout=10)
    except Exception:
        proc.kill()


def main() -> int:
    parser = argparse.ArgumentParser(description="Supervise Exegol backend/frontend processes.")
    parser.add_argument("--repo-root", default=os.getcwd())
    parser.add_argument("--startup-timeout", type=int, default=45)
    parser.add_argument("--poll-seconds", type=int, default=5)
    args = parser.parse_args()

    root = Path(args.repo_root).resolve()
    logs_dir = root / ".exegol" / "logs"
    logs_dir.mkdir(parents=True, exist_ok=True)
    api_key = os.getenv("EXEGOL_API_KEY", "dev-local-key")

    venv_python = root / ".venv" / "Scripts" / "python.exe"
    python_exe = str(venv_python if venv_python.exists() else sys.executable)
    backend_cmd = [python_exe, "api.py"]
    backend_env = os.environ.copy()
    backend_env["EXEGOL_DEFER_MISSED_JOBS"] = "1"
    frontend_cmd = ["npm.cmd" if os.name == "nt" else "npm", "run", "dev", "--", "--hostname", "127.0.0.1", "--port", "3000"]
    frontend_env = os.environ.copy()
    frontend_env["PORT"] = "3000"

    processes: Dict[str, subprocess.Popen] = {
        "backend": start_process("backend", backend_cmd, root / "src", logs_dir / "backend.log", env=backend_env),
        "frontend": start_process("frontend", frontend_cmd, root / "workbench_ui", logs_dir / "frontend.log", env=frontend_env),
    }

    stopping = False

    def handle_stop(signum, frame):
        nonlocal stopping
        stopping = True

    signal.signal(signal.SIGINT, handle_stop)
    signal.signal(signal.SIGTERM, handle_stop)

    deadline = time.time() + args.startup_timeout
    backend_ready = frontend_ready = False
    while time.time() < deadline and not (backend_ready and frontend_ready):
        backend_ready = probe("http://localhost:8000/health", api_key)
        frontend_ready = probe("http://localhost:3000")
        time.sleep(1)

    state = "healthy" if backend_ready and frontend_ready else "degraded"
    print(f"[supervisor] startup {state}. API=http://localhost:8000 UI=http://localhost:3000")
    print(f"[supervisor] logs={logs_dir}")

    if not backend_ready or not frontend_ready:
        print("[supervisor] hung startup detected; continuing supervision in degraded mode.")

    while not stopping:
        for name, proc in list(processes.items()):
            if proc.poll() is not None:
                print(f"[supervisor] {name} exited with {proc.returncode}; restarting.")
                if name == "backend":
                    processes[name] = start_process(name, backend_cmd, root / "src", logs_dir / "backend.log", env=backend_env)
                else:
                    processes[name] = start_process(name, frontend_cmd, root / "workbench_ui", logs_dir / "frontend.log", env=frontend_env)
        time.sleep(args.poll_seconds)

    for proc in processes.values():
        stop_process(proc)
    print("[supervisor] stopped backend and frontend.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
