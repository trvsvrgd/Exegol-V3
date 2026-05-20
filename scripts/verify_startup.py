<<<<<<< HEAD
import json
import os
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
FRONTEND_ENV = ROOT / "workbench_ui" / ".env.local"
ROOT_ENV = ROOT / ".env"
PRIORITY_FILE = ROOT / "config" / "priority.json"
FLEET_STATE_FILE = ROOT / ".exegol" / "fleet_state.json"


def read_env(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    if not path.exists():
        return values
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip().strip('"').strip("'")
    return values


def fail(message: str) -> None:
    print(f"[StartupCheck] ERROR: {message}")
    sys.exit(1)


def warn(message: str) -> None:
    print(f"[StartupCheck] WARNING: {message}")


def repair_blocked_state() -> None:
    if not PRIORITY_FILE.exists():
        fail(f"Missing {PRIORITY_FILE}")

    config = json.loads(PRIORITY_FILE.read_text(encoding="utf-8"))
    changed = False
    root_path = str(ROOT)

    for repo in config.get("repositories", []):
        if Path(repo.get("repo_path", "")).resolve() == ROOT and repo.get("agent_status") == "blocked":
            print("[StartupCheck] Exegol repo was blocked; resetting to idle for startup retry.")
            repo["agent_status"] = "idle"
            changed = True
            break

    if changed:
        PRIORITY_FILE.write_text(json.dumps(config, indent=2), encoding="utf-8")

    if FLEET_STATE_FILE.exists():
        try:
            state = json.loads(FLEET_STATE_FILE.read_text(encoding="utf-8"))
            if state.get("status") == "blocked" and Path(state.get("active_repo", root_path)).resolve() == ROOT:
                state["last_cleared_errors"] = state.get("errors", [])
                state["active_agent"] = None
                state["status"] = "idle"
                state["handoff_chain"] = []
                state["next_agent_id"] = ""
                state["errors"] = []
                state["output_summary"] = "Blocked state cleared by startup preflight."
                FLEET_STATE_FILE.write_text(json.dumps(state, indent=4), encoding="utf-8")
        except json.JSONDecodeError:
            warn(f"Could not parse {FLEET_STATE_FILE}; leaving it unchanged.")


def main() -> None:
    print("[StartupCheck] Verifying local startup configuration...")

    required_paths = [
        ROOT / ".venv" / "Scripts" / "python.exe",
        ROOT / "src" / "api.py",
        ROOT / "workbench_ui" / "package.json",
        ROOT / "workbench_ui" / "package-lock.json",
    ]
    for path in required_paths:
        if not path.exists():
            fail(f"Missing required path: {path}")

    root_env = read_env(ROOT_ENV)
    frontend_env = read_env(FRONTEND_ENV)

    api_key = root_env.get("EXEGOL_API_KEY")
    frontend_key = frontend_env.get("NEXT_PUBLIC_API_KEY")
    if not api_key:
        fail("EXEGOL_API_KEY is missing from .env")
    if not frontend_key:
        fail("NEXT_PUBLIC_API_KEY is missing from workbench_ui\\.env.local")
    if api_key != frontend_key:
        fail("EXEGOL_API_KEY and NEXT_PUBLIC_API_KEY do not match")

    if not root_env.get("EXEGOL_HMAC_SECRET"):
        fail("EXEGOL_HMAC_SECRET is missing from .env")

    api_base = frontend_env.get("NEXT_PUBLIC_API_BASE_URL", "")
    if api_base not in {"http://127.0.0.1:8000", "http://localhost:8000"}:
        warn(f"Unexpected NEXT_PUBLIC_API_BASE_URL: {api_base}")

    repair_blocked_state()
    print("[StartupCheck] Startup configuration is ready.")


if __name__ == "__main__":
    main()
=======
import argparse
import os
import sys
from typing import Dict, Tuple

import requests


def check_url(name: str, url: str, headers: Dict[str, str] | None = None, timeout: float = 3.0) -> Tuple[bool, str]:
    try:
        response = requests.get(url, headers=headers or {}, timeout=timeout)
    except requests.RequestException as exc:
        return False, f"{name}: {exc}"
    if response.status_code >= 500:
        return False, f"{name}: HTTP {response.status_code}"
    return True, f"{name}: HTTP {response.status_code}"


def check_api_key_rejection(backend: str, api_key: str) -> Tuple[bool, str]:
    bad_key = f"{api_key}-invalid"
    try:
        response = requests.get(f"{backend}/health", headers={"X-API-Key": bad_key}, timeout=3.0)
    except requests.RequestException as exc:
        return False, f"API key rejection: {exc}"
    if response.status_code == 403:
        return True, "API key rejection: HTTP 403"
    return False, f"API key rejection: expected 403, got HTTP {response.status_code}"


def check_docker_state(backend: str, api_key: str) -> Tuple[bool, str]:
    try:
        response = requests.get(f"{backend}/health", headers={"X-API-Key": api_key}, timeout=5.0)
        response.raise_for_status()
        data = response.json()
    except Exception as exc:
        return False, f"Docker state: unable to read /health ({exc})"
    docker = data.get("docker", {})
    status = docker.get("status", "unknown")
    if status == "healthy":
        return True, "Docker state: healthy"
    return True, f"Docker state: {status} ({docker.get('detail', 'no detail')})"


def main() -> int:
    parser = argparse.ArgumentParser(description="Verify Exegol startup contract.")
    parser.add_argument("--backend", default=os.getenv("EXEGOL_BACKEND_URL", "http://localhost:8000"))
    parser.add_argument("--frontend", default=os.getenv("EXEGOL_FRONTEND_URL", "http://localhost:3000"))
    parser.add_argument("--repo-path", default=os.getcwd())
    parser.add_argument("--api-key", default=os.getenv("EXEGOL_API_KEY", "dev-local-key"))
    args = parser.parse_args()

    headers = {"X-API-Key": args.api_key}
    checks = [
        check_url("backend /health", f"{args.backend}/health", headers=headers),
        check_url(
            "backend /fleet/supervisor-health",
            f"{args.backend}/fleet/supervisor-health?repo_path={requests.utils.quote(args.repo_path)}",
            headers=headers,
            timeout=8.0,
        ),
        check_url("frontend", args.frontend),
        check_api_key_rejection(args.backend, args.api_key),
        check_docker_state(args.backend, args.api_key),
    ]

    print("Exegol startup verification")
    print(f"API: {args.backend}")
    print(f"UI:  {args.frontend}")
    print("Logs: .exegol/logs/backend.log and .exegol/logs/frontend.log")
    for ok, message in checks:
        print(f"[{'OK' if ok else 'FAIL'}] {message}")

    if not all(ok for ok, _ in checks):
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
>>>>>>> ff5eaef6564eaad195d74a2ad85dae0c4034de1e
