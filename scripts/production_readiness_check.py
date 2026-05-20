import argparse
import os
import subprocess
import sys
from typing import List
import requests

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(__file__)), "src"))

from tools.backlog_manager import BacklogManager
from tools.prod_supervisor import ProdSupervisor
from tools.state_manager import StateManager
from tools.state_migrations import StateMigrationManager


def run_command(command: List[str], cwd: str) -> tuple[bool, str]:
    try:
        result = subprocess.run(command, cwd=cwd, capture_output=True, text=True, timeout=120)
    except Exception as exc:
        return False, str(exc)
    output = (result.stdout + "\n" + result.stderr).strip()
    return result.returncode == 0, output[-2000:]


def main() -> int:
    parser = argparse.ArgumentParser(description="Run Exegol production readiness checks.")
    parser.add_argument("--repo-path", default=os.getcwd())
    parser.add_argument("--skip-tests", action="store_true")
    parser.add_argument("--skip-build", action="store_true")
    parser.add_argument("--backend", default=os.getenv("EXEGOL_BACKEND_URL", "http://localhost:8000"))
    parser.add_argument("--frontend", default=os.getenv("EXEGOL_FRONTEND_URL", "http://localhost:3000"))
    parser.add_argument("--api-key", default=os.getenv("EXEGOL_API_KEY", "dev-local-key"))
    args = parser.parse_args()
    root = os.path.abspath(args.repo_path)
    reasons: List[str] = []
    degraded: List[str] = []

    sm = StateManager(root)
    migration = StateMigrationManager(root).migrate()
    if migration.get("changed"):
        degraded.append(f"state schema migration changed {len(migration['changed'])} file(s)")

    backlog = sm.read_json(".exegol/backlog.json") or []
    queue = sm.read_json(".exegol/user_action_required.json") or []
    pending_blockers = [item for item in queue if item.get("status") != "done"]
    if pending_blockers:
        reasons.append(f"{len(pending_blockers)} pending blocker/HITL item(s)")

    dedupe = BacklogManager(root).dedupe_auto_failures()
    if dedupe.get("removed_duplicates", 0):
        degraded.append(f"deduped {dedupe['removed_duplicates']} duplicate backlog failure(s)")

    corruption_events = sm.read_json(".exegol/corruption_events.json") or []
    if corruption_events:
        degraded.append(f"{len(corruption_events)} JSON corruption recovery event(s)")

    if not args.skip_tests:
        ok, output = run_command([sys.executable, "-m", "pytest", "tests/test_prod_supervisor.py", "tests/test_state_manager.py", "tests/test_operations.py", "tests/test_scheduler_hardening.py", "tests/test_state_migrations.py", "-q", "--basetemp", ".pytest_tmp/readiness"], root)
        if not ok:
            reasons.append("targeted tests failed")
            print(output)

    if not args.skip_build:
        ok, output = run_command(["npm.cmd" if os.name == "nt" else "npm", "run", "build"], os.path.join(root, "workbench_ui"))
        if not ok:
            reasons.append("frontend build failed")
            print(output)

    supervisor_state = ProdSupervisor(str(root)).run_once()
    if supervisor_state.get("status") != "healthy":
        degraded.append("supervisor health is degraded")

    try:
        health = requests.get(f"{args.backend}/health", headers={"X-API-Key": args.api_key}, timeout=3).json()
        if health.get("env", {}).get("status") == "degraded":
            degraded.append("environment health is degraded")
    except Exception:
        degraded.append("live backend startup check unavailable")

    if reasons:
        print("BLOCKED")
        for reason in reasons:
            print(f"- {reason}")
        return 2
    if degraded:
        print("DEGRADED")
        for reason in degraded:
            print(f"- {reason}")
        return 1
    print("READY")
    print("- startup contract, state integrity, supervisor checks, and blocker scan passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
