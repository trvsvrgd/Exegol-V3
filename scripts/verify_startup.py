import json
import os
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
FRONTEND_ENV = ROOT / "workbench_ui" / ".env.local"
ROOT_ENV = ROOT / ".env"
PRIORITY_FILE = ROOT / "config" / "priority.json"
FLEET_STATE_FILE = ROOT / ".exegol" / "fleet_state.json"
SCHEDULER_STATE_FILE = ROOT / ".exegol" / "scheduler_state.json"
RESOLVED_CRASH_MARKERS = (
    "cannot access local variable 'time'",
    "'charmap' codec can't encode character",
)


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


def repair_blocked_state(
    root: Path = ROOT,
    priority_file: Path = PRIORITY_FILE,
    fleet_state_file: Path = FLEET_STATE_FILE,
    scheduler_state_file: Path = SCHEDULER_STATE_FILE,
) -> None:
    if not priority_file.exists():
        fail(f"Missing {priority_file}")

    config = json.loads(priority_file.read_text(encoding="utf-8"))
    changed = False
    root_path = str(root)

    for repo in config.get("repositories", []):
        if Path(repo.get("repo_path", "")).resolve() == root and repo.get("agent_status") == "blocked":
            print("[StartupCheck] Exegol repo was blocked; resetting to idle for startup retry.")
            repo["agent_status"] = "idle"
            changed = True
            break

    if changed:
        priority_file.write_text(json.dumps(config, indent=2), encoding="utf-8")

    if fleet_state_file.exists():
        try:
            state = json.loads(fleet_state_file.read_text(encoding="utf-8"))
            is_current_repo = Path(state.get("active_repo", root_path)).resolve() == root
            if state.get("status") == "blocked" and is_current_repo:
                state["last_cleared_errors"] = state.get("errors", [])
                state["active_agent"] = None
                state["status"] = "idle"
                state["handoff_chain"] = []
                state["next_agent_id"] = ""
                state["errors"] = []
                state["output_summary"] = "Blocked state cleared by startup preflight."
                fleet_state_file.write_text(json.dumps(state, indent=4), encoding="utf-8")
            elif is_current_repo and not state.get("errors"):
                output_summary = str(state.get("output_summary") or "")
                if any(marker in output_summary for marker in RESOLVED_CRASH_MARKERS):
                    state["last_cleared_output_summary"] = output_summary
                    state["active_agent"] = None
                    state["status"] = "idle"
                    state["handoff_chain"] = []
                    state["next_agent_id"] = ""
                    state["output_summary"] = "Stale crash summary cleared by startup preflight."
                    fleet_state_file.write_text(json.dumps(state, indent=4), encoding="utf-8")
        except json.JSONDecodeError:
            warn(f"Could not parse {fleet_state_file}; leaving it unchanged.")

    if scheduler_state_file.exists():
        try:
            scheduler_state = json.loads(scheduler_state_file.read_text(encoding="utf-8"))
            if scheduler_state.get("status") == "healthy" and scheduler_state.get("enabled") is True:
                scheduler_state.update(
                    {
                        "status": "stopped",
                        "detail": "Cleared stale scheduler heartbeat by startup preflight.",
                        "enabled": False,
                        "heartbeat": None,
                    }
                )
                scheduler_state_file.write_text(json.dumps(scheduler_state, indent=4), encoding="utf-8")
        except json.JSONDecodeError:
            warn(f"Could not parse {scheduler_state_file}; leaving it unchanged.")


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

    if not root_env.get("SLACK_BOT_TOKEN") or not root_env.get("SLACK_APP_TOKEN"):
        fail("SLACK_BOT_TOKEN and SLACK_APP_TOKEN are required in .env for production HITL")

    api_base = frontend_env.get("NEXT_PUBLIC_API_BASE_URL", "")
    if api_base not in {"http://127.0.0.1:8000", "http://localhost:8000"}:
        warn(f"Unexpected NEXT_PUBLIC_API_BASE_URL: {api_base}")

    repair_blocked_state()
    print("[StartupCheck] Startup configuration is ready.")


if __name__ == "__main__":
    main()
