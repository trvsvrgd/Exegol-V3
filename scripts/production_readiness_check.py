import argparse
import datetime
import os
import subprocess
import sys
from typing import List
from urllib.parse import urljoin

import requests
from dotenv import load_dotenv

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


def check_backend_health(backend_url: str, api_key: str) -> List[str]:
    try:
        response = requests.get(f"{backend_url.rstrip('/')}/health", headers={"X-API-Key": api_key}, timeout=3)
        if response.status_code < 200 or response.status_code >= 400:
            return [f"live backend health check returned HTTP {response.status_code}"]
        health = response.json()
    except Exception as exc:
        return [f"live backend startup check unavailable: {exc}"]

    if health.get("env", {}).get("status") == "degraded":
        return ["environment health is degraded"]
    return []


def _frontend_response_diagnostic(response: requests.Response) -> str:
    body = response.text[:2000] if getattr(response, "text", None) else ""
    if "React Client Manifest" in body or "global-error.js" in body:
        return (
            " (Next.js client manifest appears stale; clear workbench_ui\\.next\\dev "
            "with scripts\\workbench_frontend_preflight.py --mode development --repair-cache and restart the frontend)"
        )
    return ""


def check_frontend_routes(frontend_url: str, routes: List[str]) -> List[str]:
    findings: List[str] = []
    base = frontend_url.rstrip("/") + "/"
    for route in routes:
        route_path = route.lstrip("/")
        url = urljoin(base, route_path)
        try:
            response = requests.get(url, timeout=5)
        except requests.Timeout:
            findings.append(
                f"frontend route unavailable: {route} "
                "(timed out; restart the frontend after clearing the generated Next.js cache)"
            )
            continue
        except Exception as exc:
            findings.append(f"frontend route unavailable: {route} ({exc})")
            continue
        if response.status_code < 200 or response.status_code >= 400:
            findings.append(
                f"frontend route {route} returned HTTP {response.status_code}"
                f"{_frontend_response_diagnostic(response)}"
            )
    return findings


def main() -> int:
    parser = argparse.ArgumentParser(description="Run Exegol production readiness checks.")
    parser.add_argument("--repo-path", default=os.getcwd())
    parser.add_argument("--skip-tests", action="store_true")
    parser.add_argument("--skip-build", action="store_true")
    parser.add_argument("--backend", default=os.getenv("EXEGOL_BACKEND_URL", "http://localhost:8000"))
    parser.add_argument("--frontend", default=os.getenv("EXEGOL_FRONTEND_URL", "http://127.0.0.1:3000"))
    parser.add_argument("--frontend-routes", nargs="*", default=["/", "/fleet", "/operations"])
    parser.add_argument("--api-key", default=os.getenv("EXEGOL_API_KEY", "dev-local-key"))
    args = parser.parse_args()
    root = os.path.abspath(args.repo_path)
    load_dotenv(os.path.join(root, ".env"))
    reasons: List[str] = []
    degraded: List[str] = []

    sm = StateManager(root)
    migration = StateMigrationManager(root).migrate()
    if migration.get("changed"):
        degraded.append(f"state schema migration changed {len(migration['changed'])} file(s)")

    dedupe = BacklogManager(root).dedupe_auto_failures()
    if dedupe.get("removed_duplicates", 0):
        degraded.append(f"deduped {dedupe['removed_duplicates']} duplicate backlog failure(s)")

    corruption_events = sm.read_json(".exegol/corruption_events.json") or []
    if corruption_events:
        degraded.append(f"{len(corruption_events)} JSON corruption recovery event(s)")

    if not args.skip_tests:
        stamp = datetime.datetime.now().strftime("%Y%m%d%H%M%S")
        basetemp = os.path.join(".pytest_tmp", f"readiness_{stamp}")
        cache_dir = os.path.join(".pytest_tmp", f"cache_{stamp}")
        ok, output = run_command([
            sys.executable,
            "-m",
            "pytest",
            "tests/test_prod_supervisor.py",
            "tests/test_state_manager.py",
            "tests/test_operations.py",
            "tests/test_scheduler_hardening.py",
            "tests/test_state_migrations.py",
            "-q",
            "--basetemp",
            basetemp,
            "-o",
            f"cache_dir={cache_dir}",
        ], root)
        if not ok:
            reasons.append("targeted tests failed")
            print(output)

    if not args.skip_build:
        ok, output = run_command(["npm.cmd" if os.name == "nt" else "npm", "run", "build"], os.path.join(root, "workbench_ui"))
        if not ok:
            reasons.append("frontend build failed")
            print(output)

    supervisor_state = ProdSupervisor(str(root), persist_blockers=False).run_once()
    if supervisor_state.get("status") != "healthy":
        degraded.append("supervisor health is degraded")

    queue = sm.read_json(".exegol/user_action_required.json") or []
    production_blockers = [
        item
        for item in queue
        if item.get("status") != "done" and item.get("category") == "blocker"
    ]
    if production_blockers:
        reasons.append(f"{len(production_blockers)} pending production blocker(s)")

    if not os.getenv("SLACK_BOT_TOKEN") or not os.getenv("SLACK_APP_TOKEN"):
        reasons.append("Slack bot/app tokens are required for production HITL")

    degraded.extend(check_backend_health(args.backend, args.api_key))
    degraded.extend(check_frontend_routes(args.frontend, args.frontend_routes))

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
