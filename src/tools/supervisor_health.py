import json
import os
import subprocess
import urllib.error
import urllib.request
from datetime import datetime
from typing import Any, Dict, List, Optional

from tools.state_manager import StateManager


DEFAULT_HEARTBEAT_TTL_SECONDS = 300
DEFAULT_ENDPOINT_TIMEOUT_SECONDS = 2


def _service(status: str, detail: str, **extra: Any) -> Dict[str, Any]:
    payload = {"status": status, "detail": detail}
    payload.update(extra)
    return payload


def persist_supervisor_event(repo_path: str, event_type: str, detail: str, **extra: Any) -> Dict[str, Any]:
    """Append a supervisor event under .exegol for post-restart diagnosis."""
    event = {
        "timestamp": datetime.now().isoformat(),
        "event_type": event_type,
        "detail": detail,
    }
    event.update(extra)

    event_dir = os.path.join(repo_path, ".exegol")
    event_path = os.path.join(event_dir, "supervisor_events.jsonl")
    try:
        os.makedirs(event_dir, exist_ok=True)
        with open(event_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(event, sort_keys=True) + "\n")
    except OSError as exc:
        print(f"[SupervisorHealth] Failed to persist supervisor event: {exc}")
    return event


def check_http_endpoint(name: str, url: Optional[str], timeout_seconds: int = DEFAULT_ENDPOINT_TIMEOUT_SECONDS) -> Dict[str, Any]:
    """Check a local service endpoint without attempting process recovery."""
    if not url:
        return _service("disabled", f"{name} endpoint supervision is not configured.", policy="report_only")

    try:
        request = urllib.request.Request(url, method="GET")
        with urllib.request.urlopen(request, timeout=timeout_seconds) as response:
            status_code = getattr(response, "status", response.getcode())
    except urllib.error.HTTPError as exc:
        if exc.code < 500:
            return _service("ok", f"{name} endpoint is reachable with HTTP {exc.code}.", url=url, status_code=exc.code, policy="report_only")
        return _service("degraded", f"{name} endpoint returned HTTP {exc.code}.", url=url, status_code=exc.code, policy="report_only")
    except Exception as exc:
        return _service("degraded", f"{name} endpoint is unreachable: {type(exc).__name__}: {exc}", url=url, policy="report_only")

    if status_code >= 500:
        return _service("degraded", f"{name} endpoint returned HTTP {status_code}.", url=url, status_code=status_code, policy="report_only")
    return _service("ok", f"{name} endpoint is reachable with HTTP {status_code}.", url=url, status_code=status_code, policy="report_only")


def check_docker(timeout_seconds: int = 3) -> Dict[str, Any]:
    """Return Docker daemon health without requiring interactive recovery."""
    try:
        result = subprocess.run(
            ["docker", "info"],
            capture_output=True,
            text=True,
            timeout=timeout_seconds,
        )
    except FileNotFoundError:
        return _service("degraded", "Docker CLI was not found on PATH.", policy="blocked_manual")
    except subprocess.TimeoutExpired:
        return _service("degraded", f"docker info timed out after {timeout_seconds}s.", policy="blocked_manual")
    except Exception as exc:
        return _service("degraded", f"Docker health check failed: {type(exc).__name__}: {exc}", policy="blocked_manual")

    if result.returncode != 0:
        detail = (result.stderr or result.stdout or "docker info returned a non-zero exit code.").strip()
        return _service("degraded", detail[:500], policy="blocked_manual")

    return _service("ok", "Docker daemon is reachable.", policy="report_only")


def scan_heartbeats(repo_path: str, ttl_seconds: int = DEFAULT_HEARTBEAT_TTL_SECONDS) -> Dict[str, Any]:
    """Inspect persisted heartbeat files and report stale active sessions."""
    heartbeat_dir = os.path.join(repo_path, ".exegol", "heartbeats")
    if not os.path.isdir(heartbeat_dir):
        return _service("ok", "No active heartbeat directory found.", active=0, stale=0, historical_stale=0, total=0, sessions=[])

    sessions: List[Dict[str, Any]] = []
    stale_count = 0
    active_count = 0
    historical_stale_count = 0
    now = datetime.now()

    for filename in sorted(os.listdir(heartbeat_dir)):
        if not filename.endswith(".json"):
            continue
        path = os.path.join(heartbeat_dir, filename)
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
        except (OSError, json.JSONDecodeError) as exc:
            sessions.append({
                "session_id": filename.removesuffix(".json"),
                "status": "unreadable",
                "detail": f"{type(exc).__name__}: {exc}",
                "blocking": True,
            })
            stale_count += 1
            continue

        last_pulse = data.get("last_pulse")
        age_seconds: Optional[float] = None
        raw_status = data.get("status", "unknown")
        blocking_stale = raw_status == "zombie"
        historical_stale = raw_status == "stale"
        if last_pulse:
            try:
                age_seconds = (now - datetime.fromisoformat(last_pulse)).total_seconds()
                blocking_stale = blocking_stale or (raw_status == "active" and age_seconds > ttl_seconds)
            except ValueError:
                blocking_stale = True

        if blocking_stale:
            stale_count += 1
        elif historical_stale:
            historical_stale_count += 1
        elif raw_status == "active":
            active_count += 1

        sessions.append({
            "session_id": data.get("session_id", filename.removesuffix(".json")),
            "agent_id": data.get("agent_id", "unknown"),
            "status": "stale" if blocking_stale or historical_stale else raw_status,
            "blocking": blocking_stale,
            "age_seconds": round(age_seconds, 1) if age_seconds is not None else None,
            "last_pulse": last_pulse,
        })

    total_count = len(sessions)
    if stale_count:
        return _service(
            "degraded",
            f"{stale_count} active heartbeat session(s) need review.",
            active=active_count,
            stale=stale_count,
            historical_stale=historical_stale_count,
            total=total_count,
            sessions=sessions,
        )

    detail = "Heartbeat files are current."
    if historical_stale_count:
        detail = f"Heartbeat files are current; {historical_stale_count} stale heartbeat record(s) already acknowledged."
    return _service(
        "ok",
        detail,
        active=active_count,
        stale=0,
        historical_stale=historical_stale_count,
        total=total_count,
        sessions=sessions,
    )


def _acknowledge_stale_heartbeat_records(repo_path: str, stale_sessions: List[Dict[str, Any]]) -> None:
    """Mark blocking stale heartbeat files as acknowledged so they do not re-block repeatedly."""
    heartbeat_dir = os.path.join(repo_path, ".exegol", "heartbeats")
    if not os.path.isdir(heartbeat_dir):
        return

    acknowledged_at = datetime.now().isoformat()
    for session in stale_sessions:
        session_id = session.get("session_id")
        if not session_id or session.get("status") == "unreadable":
            continue

        heartbeat_path = os.path.join(heartbeat_dir, f"{session_id}.json")
        if not os.path.exists(heartbeat_path):
            continue

        try:
            with open(heartbeat_path, "r", encoding="utf-8") as f:
                heartbeat = json.load(f)
            if heartbeat.get("status") not in {"active", "zombie"}:
                continue
            heartbeat["status"] = "stale"
            heartbeat.setdefault("stale_detected_at", acknowledged_at)
            if session.get("age_seconds") is not None:
                heartbeat["stale_age_seconds"] = session["age_seconds"]
            heartbeat["acknowledge_reason"] = "Supervisor converted stale heartbeat to blocked fleet state."
            with open(heartbeat_path, "w", encoding="utf-8") as f:
                json.dump(heartbeat, f, indent=2)
        except (OSError, json.JSONDecodeError) as exc:
            print(f"[SupervisorHealth] Failed to acknowledge heartbeat {session_id}: {exc}")


def read_fleet_state(repo_path: str) -> Dict[str, Any]:
    state_file = os.path.join(repo_path, ".exegol", "fleet_state.json")
    if not os.path.exists(state_file):
        return _service("ok", "No fleet_state.json exists yet.", state=None)

    try:
        with open(state_file, "r", encoding="utf-8") as f:
            state = json.load(f)
    except (OSError, json.JSONDecodeError) as exc:
        return _service("degraded", f"fleet_state.json is unreadable: {type(exc).__name__}: {exc}", state=None)

    if state.get("status") == "blocked":
        return _service("blocked", "Fleet state is blocked.", state=state)
    return _service("ok", f"Fleet state is {state.get('status', 'unknown')}.", state=state)


def reconcile_stale_heartbeats(repo_path: str, heartbeat_health: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Turn stale heartbeat health into truthful blocked fleet state."""
    if heartbeat_health.get("status") != "degraded" or not heartbeat_health.get("stale"):
        return None

    sm = StateManager(repo_path)
    existing = sm.read_fleet_state()

    stale_sessions = [
        session for session in heartbeat_health.get("sessions", [])
        if session.get("blocking") or session.get("status") == "unreadable"
    ]
    if not stale_sessions:
        return None

    if existing.get("status") == "blocked" and existing.get("blocker_type") == "stale_heartbeat":
        _acknowledge_stale_heartbeat_records(repo_path, stale_sessions)
        return existing

    first = stale_sessions[0] if stale_sessions else {}
    agent_id = first.get("agent_id", "unknown")
    session_id = first.get("session_id", "")
    message = f"Supervisor detected stale heartbeat for {agent_id} session {session_id}."
    errors = [message]

    state = {
        "active_repo": repo_path,
        "active_agent": agent_id,
        "session_id": session_id,
        "status": "blocked",
        "started_at": datetime.now().isoformat(),
        "handoff_chain": existing.get("handoff_chain", []),
        "next_agent_id": "",
        "monologue": existing.get("monologue", []),
        "errors": errors,
        "output_summary": message,
        "retry_available": True,
        "failure_logged_at": datetime.now().isoformat(),
        "blocker_type": "stale_heartbeat",
    }
    sm.write_fleet_state(state)
    _acknowledge_stale_heartbeat_records(repo_path, stale_sessions)
    persist_supervisor_event(
        repo_path,
        "stale_session_blocked",
        message,
        severity="error",
        target="heartbeat",
        action="blocked_repo",
        agent_id=agent_id,
        session_id=session_id,
    )

    try:
        from tools.fleet_logger import log_interaction
        log_interaction(
            agent_id="supervisor",
            outcome="failure",
            task_summary=message,
            repo_path=repo_path,
            errors=errors,
            state_changes={"blocker_type": "stale_heartbeat"},
        )
    except Exception as exc:
        print(f"[SupervisorHealth] Failed to log stale heartbeat blocker: {exc}")

    return state


def _supervisor_event_repo(orchestrator: Any, repos: List[Dict[str, Any]]) -> str:
    configured = os.getenv("EXEGOL_REPO_PATH")
    if configured:
        return configured
    for repo in repos:
        if repo.get("repo_path"):
            return repo["repo_path"]
    return os.getcwd()


def remediate_scheduler(orchestrator: Any, event_repo: str) -> Dict[str, Any]:
    """Restart the in-process scheduler when it is expected but dead."""
    restart = getattr(orchestrator, "restart_scheduler", None)
    if callable(restart):
        restarted = bool(restart())
    else:
        setup = getattr(orchestrator, "_setup_cadence_engine", None)
        if not callable(setup):
            return _service("degraded", "Scheduler is dead and no restart hook is available.", policy="report_only", action="reported")
        setattr(orchestrator, "_should_stop_scheduler", False)
        setup()
        scheduler_thread = getattr(orchestrator, "scheduler_thread", None)
        restarted = bool(scheduler_thread and scheduler_thread.is_alive())

    scheduler_thread = getattr(orchestrator, "scheduler_thread", None)
    if restarted and scheduler_thread and scheduler_thread.is_alive():
        detail = "Scheduler thread was dead and was restarted by supervisor."
        persist_supervisor_event(
            event_repo,
            "scheduler_restarted",
            detail,
            severity="warning",
            target="scheduler",
            action="auto_restart",
        )
        return _service("ok", detail, policy="auto_restart", action="restarted")

    detail = "Scheduler thread is dead and supervisor restart did not recover it."
    persist_supervisor_event(
        event_repo,
        "scheduler_restart_failed",
        detail,
        severity="error",
        target="scheduler",
        action="reported",
    )
    return _service("degraded", detail, policy="auto_restart", action="restart_failed")


def build_supervisor_health(
    orchestrator: Any,
    autonomous_status: Dict[str, Any],
    *,
    perform_endpoint_checks: bool = False,
    perform_remediation: bool = True,
    backend_url: Optional[str] = None,
    frontend_url: Optional[str] = None,
) -> Dict[str, Any]:
    """Aggregate service health for UI and readiness checks."""
    orchestrator.load_config()
    repos = orchestrator.priority_config.get("repositories", [])
    event_repo = _supervisor_event_repo(orchestrator, repos)
    scheduler_thread = getattr(orchestrator, "scheduler_thread", None)
    scheduler_disabled = os.getenv("EXEGOL_DISABLE_SCHEDULER", "").lower() in {"1", "true", "yes"}
    scheduler_alive = bool(scheduler_thread and scheduler_thread.is_alive())

    services: Dict[str, Any] = {
        "backend": check_http_endpoint(
            "Backend",
            backend_url or os.getenv("EXEGOL_BACKEND_HEALTH_URL") if perform_endpoint_checks else None,
        ),
        "frontend": check_http_endpoint(
            "Frontend",
            frontend_url or os.getenv("EXEGOL_FRONTEND_URL", "http://127.0.0.1:3000") if perform_endpoint_checks else None,
        ),
        "autonomous_loop": _service(
            "ok" if not autonomous_status.get("continuous_mode") or autonomous_status.get("thread_alive") else "degraded",
            "Autonomous loop is active." if autonomous_status.get("thread_alive") else "Autonomous loop is stopped.",
            policy="report_only",
            **autonomous_status,
        ),
        "scheduler": _service(
            "disabled" if scheduler_disabled else ("ok" if scheduler_alive else "degraded"),
            "Scheduler disabled by environment." if scheduler_disabled else (
                "Scheduler thread is alive." if scheduler_alive else "Scheduler thread is not running."
            ),
            policy="disabled" if scheduler_disabled else "auto_restart",
        ),
        "docker": check_docker(),
    }

    if services["scheduler"]["status"] == "degraded" and perform_remediation:
        services["scheduler"] = remediate_scheduler(orchestrator, event_repo)

    for name, service in services.items():
        if service.get("status") == "degraded":
            persist_supervisor_event(
                event_repo,
                f"{name}_degraded",
                service.get("detail", f"{name} is degraded."),
                severity="error",
                target=name,
                action=service.get("policy", "report_only"),
            )

    repo_reports = []
    for repo in repos:
        repo_path = repo.get("repo_path", "")
        heartbeat_health = scan_heartbeats(repo_path)
        reconcile_stale_heartbeats(repo_path, heartbeat_health)
        state_health = read_fleet_state(repo_path)
        repo_status = "ok"
        if state_health["status"] in {"blocked", "degraded"} or heartbeat_health["status"] == "degraded":
            repo_status = "degraded"
        repo_reports.append({
            "name": os.path.basename(repo_path),
            "path": repo_path,
            "configured_status": repo.get("agent_status", "idle"),
            "status": repo_status,
            "fleet_state": state_health,
            "heartbeats": heartbeat_health,
        })

    degraded_services = [
        name for name, service in services.items()
        if service.get("status") not in {"ok", "disabled"}
    ]
    degraded_repos = [repo["path"] for repo in repo_reports if repo["status"] != "ok"]
    overall = "ok" if not degraded_services and not degraded_repos else "degraded"

    return {
        "status": overall,
        "checked_at": datetime.now().isoformat(),
        "services": services,
        "repositories": repo_reports,
        "degraded_services": degraded_services,
        "degraded_repositories": degraded_repos,
    }
