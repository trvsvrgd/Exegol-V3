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
