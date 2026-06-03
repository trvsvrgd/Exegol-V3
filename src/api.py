import os
import json
import uuid
import datetime
import uvicorn
import requests
import threading
import time
from urllib.parse import urlparse
from concurrent.futures import ThreadPoolExecutor
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse
from pydantic import BaseModel
from typing import List, Optional, Dict, Any

from orchestrator import ExegolOrchestrator
from agents.registry import AGENT_REGISTRY
from tools.state_manager import StateManager
from tools.thrawn_intel_manager import ThrawnIntelManager
from tools.egress_filter import EgressFilter
from tools.fleet_logger import read_interaction_logs
from tools.metrics_manager import (
    DEFAULT_METRICS_START_DATE,
    SuccessMetricsManager,
    calculate_read_days_for_start,
    filter_logs_since,
    parse_metrics_start_date,
)
from tools.tool_registry import ToolRegistry
from tools.hitl_manager import HITLManager
from tools.operations import get_backend_process_state, is_retry_allowed
from tools.supervisor_health import build_supervisor_health, reconcile_stale_heartbeats, scan_heartbeats
from tools.backlog_manager import BacklogManager
from tools.objective_manager import ObjectiveManager
from tools.poe_roadmap_brief import load_or_build_poe_roadmap_brief
from tools.repo_discovery import register_repository, sync_discovered_repositories
from tools.fleet_runtime_control import resume_runtime

ROOT_DIR = os.path.abspath(os.path.dirname(os.path.dirname(__file__)))


def load_runtime_environment(root_path: str = ROOT_DIR) -> None:
    load_dotenv(os.path.join(root_path, ".env"))


load_runtime_environment()

# ---------------------------------------------------------------------------
# App Setup
# ---------------------------------------------------------------------------

app = FastAPI(title="Exegol V3 - Control Tower Backend")

# Enable CORS for Control Tower UI
ALLOWED_ORIGINS = [
    "http://localhost:3000",
    "http://127.0.0.1:3000",
    os.getenv("EXEGOL_FRONTEND_URL", "http://localhost:3001") # Support custom frontend ports
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---------------------------------------------------------------------------
# Task 2 — API Key Authentication Middleware (arch_api_auth_layer)
# ---------------------------------------------------------------------------

# Public endpoints that do NOT require authentication
_PUBLIC_PATHS = {"/", "/health", "/docs", "/openapi.json", "/redoc"}

API_KEY = os.getenv("EXEGOL_API_KEY")


class APIKeyMiddleware(BaseHTTPMiddleware):
    """Validates X-API-Key header on all non-public endpoints."""

    async def dispatch(self, request: Request, call_next):
        if request.method == "OPTIONS" or request.url.path in _PUBLIC_PATHS:
            return await call_next(request)

        provided_key = request.headers.get("X-API-Key", "")
        if provided_key != API_KEY:
            return JSONResponse(
                status_code=403,
                content={"detail": "Forbidden: invalid or missing X-API-Key header."},
            )
        return await call_next(request)


app.add_middleware(APIKeyMiddleware)

orchestrator = ExegolOrchestrator()

# ---------------------------------------------------------------------------
# Task 1 — Async Task Tracking Store (dev_dex_refactor_orchestrator)
# ---------------------------------------------------------------------------

# In-memory store: session_id -> {status, result, started_at, finished_at}
_running_tasks: Dict[str, Dict[str, Any]] = {}
_executor = ThreadPoolExecutor(max_workers=4)

class RepoRequest(BaseModel):
    repo_path: str


class BlockerActionRequest(BaseModel):
    repo_path: str
    blocker_id: str


def _execute_agent_sync(session_id: str, repo_path: str, agent_id: str, model: str):
    """Runs in a background thread — updates _running_tasks on completion."""
    _running_tasks[session_id]["status"] = "running"
    try:
        result = orchestrator.wake_and_execute_agent(
            repo_info={"repo_path": repo_path},
            routing=model,
            max_steps=20,
            agent_id=agent_id,
        )
        _running_tasks[session_id].update({
            "status": "done",
            "result": result.to_dict() if result else {
                "outcome": "failure",
                "output_summary": "Orchestrator blocked execution (Check Loop Guard/Circuit Breaker).",
                "errors": ["No result returned from agent execution."],
                "session_id": session_id,
                "agent_id": agent_id,
                "steps_used": 0
            },
            "finished_at": datetime.datetime.now().isoformat(),
        })
    except Exception as exc:
        _running_tasks[session_id].update({
            "status": "error",
            "result": {"error": str(exc)},
            "finished_at": datetime.datetime.now().isoformat(),
        })


# --- Fleet Continuous Execution ---

_continuous_mode = False
_continuous_fleet_thread = None
_continuous_repo_path: Optional[str] = None
_continuous_cycle_active = False
_continuous_lock = threading.Lock()

# --- Active Objective Loops Registry ---
_active_objective_loops: Dict[str, Dict[str, Any]] = {}
_objective_loops_lock = threading.Lock()
OBJECTIVE_LOOP_STOP_PHASES = {"done", "failed_budget", "blocked_human"}


def _objective_loop_should_stop(repo_path: str) -> bool:
    objective = ObjectiveManager(repo_path).load()
    if not str(objective.get("goal") or "").strip():
        return False
    return str(objective.get("phase") or "").lower() in OBJECTIVE_LOOP_STOP_PHASES


def _stop_all_objective_loops() -> int:
    with _objective_loops_lock:
        loops = list(_active_objective_loops.values())
        _active_objective_loops.clear()
    for loop in loops:
        event = loop.get("event")
        if event:
            event.set()
    return len(loops)

def _objective_loop_for_repo(repo_path: str, stop_event: threading.Event):
    try:
        while not stop_event.is_set():
            print(f"[API] Running objective loop cycle for {repo_path}...")
            try:
                orchestrator.run_fleet_cycle(repo_path=repo_path)
            except Exception as e:
                print(f"[API] Error in objective loop for {repo_path}: {e}")

            if _objective_loop_should_stop(repo_path):
                print(f"[API] Objective loop reached terminal phase for {repo_path}; stopping loop.")
                break

            for _ in range(10):
                if stop_event.is_set():
                    break
                time.sleep(1)
    finally:
        with _objective_loops_lock:
            current = _active_objective_loops.get(repo_path)
            if current and current.get("event") is stop_event:
                _active_objective_loops.pop(repo_path, None)

def _continuous_fleet_loop():
    global _continuous_mode, _continuous_cycle_active, _continuous_repo_path
    while True:
        with _continuous_lock:
            if not _continuous_mode:
                break
            repo_path = _continuous_repo_path

        with _continuous_lock:
            _continuous_cycle_active = True
        try:
            if repo_path:
                print(f"[API] Running continuous fleet cycle for {repo_path}...")
                orchestrator.run_fleet_cycle(
                    repo_path=repo_path,
                    include_due_scheduled=True,
                    trigger_source="manual_run",
                )
            else:
                print("[API] Running continuous fleet cycle...")
                orchestrator.run_fleet_cycle(
                    include_due_scheduled=True,
                    trigger_source="manual_run",
                )
        finally:
            with _continuous_lock:
                _continuous_cycle_active = False

        if repo_path and _objective_loop_should_stop(repo_path):
            with _continuous_lock:
                if _continuous_repo_path == repo_path:
                    _continuous_mode = False
                    _continuous_repo_path = None
            print(f"[API] Continuous fleet loop reached terminal objective phase for {repo_path}; stopping loop.")
            return

        for _ in range(10):
            with _continuous_lock:
                if not _continuous_mode:
                    return
            time.sleep(1)

def _autonomous_status() -> Dict[str, Any]:
    with _continuous_lock:
        continuous_mode = _continuous_mode
        repo_path = _continuous_repo_path
        cycle_active = _continuous_cycle_active
        thread_alive = bool(_continuous_fleet_thread and _continuous_fleet_thread.is_alive())
    cycle_running = bool(orchestrator.is_running_fleet or cycle_active)
    return {
        "continuous_mode": continuous_mode,
        "thread_alive": thread_alive,
        "cycle_running": cycle_running,
        "stopping": bool(not continuous_mode and cycle_running),
        "repo_path": repo_path,
    }


def _same_repo_path(left: Optional[str], right: Optional[str]) -> bool:
    if not left or not right:
        return False
    return os.path.abspath(left) == os.path.abspath(right)


def _repo_config_for_path(repo_path: str) -> Dict[str, Any]:
    normalized = os.path.abspath(repo_path)
    orchestrator.load_config()
    for repo in orchestrator.priority_config.get("repositories", []):
        configured = repo.get("repo_path")
        if configured and os.path.abspath(configured) == normalized:
            return dict(repo)
    return {}


def _autonomous_context_for_repo(repo_path: str) -> Dict[str, Any]:
    status = _autonomous_status()
    selected = _same_repo_path(status.get("repo_path"), repo_path)
    if status.get("stopping"):
        loop_status = "stopping"
    elif not status.get("continuous_mode"):
        loop_status = "stopped"
    elif status.get("cycle_running") and selected:
        loop_status = "running_selected_repo"
    elif status.get("cycle_running"):
        loop_status = "running_other_repo"
    elif selected:
        loop_status = "waiting_between_cycles"
    else:
        loop_status = "enabled_for_other_repo"

    return {
        **status,
        "selected_repo": selected,
        "loop_status": loop_status,
    }


def _empty_fleet_state(repo_path: str, status: str = "idle") -> Dict[str, Any]:
    return {
        "active_repo": repo_path,
        "active_agent": None,
        "session_id": "",
        "status": status,
        "handoff_chain": [],
        "next_agent_id": "",
        "monologue": [],
        "errors": [],
        "output_summary": "",
    }


def _normalize_registry_agent_id(agent_id: Optional[str]) -> str:
    if not agent_id:
        return ""
    class_to_id = {
        entry.get("class"): registry_id
        for registry_id, entry in AGENT_REGISTRY.items()
        if entry.get("class")
    }
    return class_to_id.get(agent_id, agent_id)


def _recent_failure_context(repo_path: str) -> Dict[str, Any]:
    try:
        logs = read_interaction_logs([repo_path], days=30)
        logs.sort(key=lambda x: x.get("timestamp", ""), reverse=True)
        failed_logs = [l for l in logs if l.get("outcome") == "failure" or l.get("errors")]
        if failed_logs:
            last_fail = failed_logs[0]
            return {
                "active_agent": last_fail.get("agent_id"),
                "session_id": last_fail.get("session_id", ""),
                "errors": last_fail.get("errors", []),
                "output_summary": last_fail.get("task_summary", ""),
            }
    except Exception as e:
        print(f"[API] Error reading interaction logs for blocked state: {e}")
    return {}

@app.post("/fleet/start-autonomous")
def start_autonomous_fleet(req: Optional[RepoRequest] = None):
    global _continuous_mode, _continuous_fleet_thread, _continuous_repo_path
    with _continuous_lock:
        if req and req.repo_path:
            _continuous_repo_path = os.path.abspath(req.repo_path)
        resume_runtime("autonomous fleet start requested")
        orchestrator.clear_fleet_stop_request()
        _continuous_mode = True
        if _continuous_fleet_thread is None or not _continuous_fleet_thread.is_alive():
            _continuous_fleet_thread = threading.Thread(target=_continuous_fleet_loop, daemon=True)
            _continuous_fleet_thread.start()
    return {"status": "success", **_autonomous_status()}

@app.post("/fleet/stop-autonomous")
def stop_autonomous_fleet():
    global _continuous_mode, _continuous_repo_path
    with _continuous_lock:
        _continuous_mode = False
        _continuous_repo_path = None
    stopped_objective_loops = _stop_all_objective_loops()
    orchestrator.request_fleet_stop("autonomous fleet stop requested from API")
    return {"status": "success", "objective_loops_stopped": stopped_objective_loops, **_autonomous_status()}

@app.post("/fleet/toggle-autonomous")
def toggle_autonomous_fleet(req: Dict[str, Any] = None):
    global _continuous_mode, _continuous_fleet_thread
    requested = None if req is None else req.get("enabled")
    if requested is True:
        repo_path = req.get("repo_path") if req else None
        return start_autonomous_fleet(RepoRequest(repo_path=repo_path) if repo_path else None)
    if requested is False:
        return stop_autonomous_fleet()

    with _continuous_lock:
        should_start = not _continuous_mode

    if should_start:
        return start_autonomous_fleet()
    return stop_autonomous_fleet()

@app.get("/fleet/autonomous-status")
def get_autonomous_status():
    return _autonomous_status()

@app.get("/fleet/supervisor-health")
def get_supervisor_health():
    return build_supervisor_health(
        orchestrator,
        _autonomous_status(),
        perform_endpoint_checks=True,
        backend_url=os.getenv("EXEGOL_BACKEND_HEALTH_URL", "http://127.0.0.1:8000/health"),
        frontend_url=os.getenv("EXEGOL_FRONTEND_URL", "http://127.0.0.1:3000"),
    )

@app.get("/fleet/operations")
def get_fleet_operations(repo_path: str):
    repo_path = os.path.abspath(repo_path)
    sm = StateManager(repo_path)
    supervisor_state = sm.read_json(".exegol/supervisor_state.json") or {}
    fleet_state = sm.read_fleet_state()
    scheduler_state = sm.read_json(".exegol/scheduler_state.json") or {}
    queue = HITLManager(repo_path).get_queue()
    backlog = BacklogManager(repo_path).load_backlog()

    pending_queue = [item for item in queue if item.get("status") != "done"]
    latest_blocker = next(
        (
            item
            for item in pending_queue
            if item.get("category") == "blocker" or item.get("blocker_type")
        ),
        None,
    )
    active_backlog = [
        item
        for item in backlog
        if item.get("status") not in {"done", "completed", "archived", "dismissed"}
    ]
    recent_logs = read_interaction_logs([repo_path], days=30)
    recent_logs.sort(key=lambda item: item.get("timestamp", ""), reverse=True)
    recent_failures = [
        {
            "timestamp": item.get("timestamp"),
            "agent_id": item.get("agent_id"),
            "outcome": item.get("outcome"),
            "errors": item.get("errors") or [],
        }
        for item in recent_logs
        if item.get("outcome") == "failure" or item.get("errors")
    ][:5]

    components = supervisor_state.get("components") or {}
    autonomous_status = _autonomous_status()
    autonomous_loop = {
        "status": "stopping"
        if autonomous_status.get("stopping")
        else "running"
        if autonomous_status.get("continuous_mode") or autonomous_status.get("cycle_running")
        else "idle"
    }
    scheduler = {
        "status": scheduler_state.get("status", components.get("scheduler", {}).get("status", "unknown")),
        "enabled": scheduler_state.get("enabled", not bool(os.getenv("EXEGOL_DISABLE_SCHEDULER"))),
        "heartbeat": scheduler_state.get("heartbeat") or scheduler_state.get("updated_at"),
    }
    due_scheduled_jobs = orchestrator.plan_due_scheduled_jobs(trigger_source="manual_run")
    status = "degraded" if latest_blocker or supervisor_state.get("status") == "degraded" else "healthy"

    return {
        "status": status,
        "backend": get_backend_process_state(),
        "components": {
            "docker": components.get("docker", {"status": "unknown"}),
            "frontend": components.get("frontend", {"status": "unknown"}),
            "scheduler": components.get("scheduler", scheduler),
        },
        "scheduler": scheduler,
        "due_scheduled_jobs": [
            {
                "id": job.get("id"),
                "agent_id": job.get("agent_id"),
                "summary": job.get("summary"),
                "reason": job.get("due_reason"),
                "run_order": job.get("run_order", job.get("_index")),
            }
            for job in due_scheduled_jobs
        ],
        "due_scheduled_count": len(due_scheduled_jobs),
        "autonomous_loop": autonomous_loop,
        "active_agent": fleet_state.get("active_agent"),
        "queue_length": len(active_backlog),
        "latest_blocker": latest_blocker,
        "latest_blocker_type": latest_blocker.get("blocker_type") if latest_blocker else None,
        "recent_failures": recent_failures,
        "health_report": supervisor_state or {"status": status, "components": components},
    }

@app.post("/blockers/clear")
def clear_blocker(req: BlockerActionRequest):
    manager = HITLManager(req.repo_path)
    if manager.resolve_task(req.blocker_id, status="done", notes="Cleared from Operations dashboard."):
        return {"status": "success", "blocker_id": req.blocker_id}
    raise HTTPException(status_code=404, detail="Blocker not found")

@app.post("/blockers/retry-go")
def retry_blocker(req: BlockerActionRequest):
    manager = HITLManager(req.repo_path)
    queue = manager.get_queue()
    blocker = next((item for item in queue if item.get("id") == req.blocker_id), None)
    if blocker is None:
        raise HTTPException(status_code=404, detail="Blocker not found")
    if not is_retry_allowed([blocker]):
        raise HTTPException(status_code=409, detail="Blocker requires manual action before retry.")

    manager.resolve_task(req.blocker_id, status="done", notes="Cleared for retry from Operations dashboard.")
    retried = orchestrator.retry_blocked_repo(req.repo_path)
    return {"status": "success", "blocker_id": req.blocker_id, "retried": retried}

@app.post("/fleet/go")
def run_fleet_once():
    started = orchestrator.run_fleet_cycle(include_due_scheduled=True, trigger_source="manual_run")
    if not started:
        return {"status": "busy_or_failed", **_autonomous_status()}
    return {"status": "success", **_autonomous_status()}

@app.post("/autonomous/start")
def start_autonomous(req: RepoRequest):
    session_id = uuid.uuid4().hex[:12]
    _running_tasks[session_id] = {
        "session_id": session_id,
        "agent_id": "fleet_cycle",
        "repo_path": req.repo_path,
        "status": "queued",
        "result": None,
        "started_at": datetime.datetime.now().isoformat(),
    }

    def _run_cycle():
        _running_tasks[session_id]["status"] = "running"
        try:
            orchestrator.run_fleet_cycle(
                repo_path=req.repo_path,
                include_due_scheduled=True,
                trigger_source="manual_run",
            )
            _running_tasks[session_id].update({
                "status": "done",
                "result": {"outcome": "success", "output_summary": "Fleet cycle completed."},
                "finished_at": datetime.datetime.now().isoformat(),
            })
        except Exception as exc:
            _running_tasks[session_id].update({
                "status": "failed",
                "result": {"outcome": "failure", "errors": [str(exc)]},
                "finished_at": datetime.datetime.now().isoformat(),
            })

    _executor.submit(_run_cycle)
    return {"status": "queued", "action": "start_autonomous", "session_id": session_id}

@app.post("/fleet/retry-blocked")
def retry_blocked_repo(req: Dict[str, Any]):
    repo_path = req.get("repo_path")
    if not repo_path:
        raise HTTPException(status_code=400, detail="Missing repo_path")

    retried = orchestrator.retry_blocked_repo(repo_path)
    if not retried:
        raise HTTPException(status_code=409, detail="Repository is not blocked or is not configured.")
    return {"status": "success", "repo_path": repo_path, "agent_status": "idle"}

@app.get("/fleet/active-state")
def get_fleet_active_state(repo_path: str):
    """Returns the real-time active state of the fleet for a repository."""
    repo_path = os.path.abspath(repo_path)
    repo_config = _repo_config_for_path(repo_path)
    repo_status = repo_config.get("agent_status", "idle")
    autonomous_context = _autonomous_context_for_repo(repo_path)

    try:
        sm = StateManager(repo_path)
        state_data = sm.read_fleet_state() or _empty_fleet_state(repo_path, repo_status)
        heartbeat_health = scan_heartbeats(repo_path)
        stale_state = reconcile_stale_heartbeats(repo_path, heartbeat_health)
        if stale_state:
            state_data = stale_state

        if repo_status == "blocked" and state_data.get("status") != "blocked":
            state_data = {**_empty_fleet_state(repo_path, "blocked"), **state_data, "status": "blocked"}

        if state_data.get("status") == "blocked":
            failure_context = _recent_failure_context(repo_path)
            if failure_context:
                if not state_data.get("active_agent"):
                    state_data["active_agent"] = failure_context.get("active_agent")
                if not state_data.get("session_id"):
                    state_data["session_id"] = failure_context.get("session_id", "")
                if not state_data.get("errors"):
                    state_data["errors"] = failure_context.get("errors", [])
                if not state_data.get("output_summary"):
                    state_data["output_summary"] = failure_context.get("output_summary", "")
        elif autonomous_context.get("loop_status") == "running_selected_repo":
            state_data["status"] = "running"
            if not state_data.get("active_agent"):
                state_data["active_agent"] = "orchestrator"
            if not state_data.get("output_summary"):
                state_data["output_summary"] = "Fleet cycle is evaluating this repository."

        state_data["repo_status"] = repo_status
        state_data["status_detail"] = repo_config.get("status_detail")
        state_data["autonomous"] = autonomous_context
        state_data["heartbeat_health"] = heartbeat_health
        return state_data
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to read fleet state: {e}")

# ---------------------------------------------------------------------------
# Pydantic Models
# ---------------------------------------------------------------------------

class RunTaskRequest(BaseModel):
    repo_path: str
    agent_id: str
    model: str
    task_prompt: str

class BacklogUpdateRequest(BaseModel):
    repo_path: str
    task_id: str
    updates: Dict[str, Any]

class ActionQueueRequest(BaseModel):
    repo_path: str
    action: str  # "done", "update_notes", "dismiss"
    item_id: str
    notes: Optional[str] = None

class ModelCompareRequest(BaseModel):
    repo_path: str
    model_names: List[str]

class SecretRotateRequest(BaseModel):
    repo_path: str
    env_var: str
    new_value: str

class AgentModelMapping(BaseModel):
    agent_id: str
    model: str

class AgentModelsRequest(BaseModel):
    mappings: List[AgentModelMapping]

class ThrawnObjectiveRequest(BaseModel):
    repo_path: str
    objective: str

class ThrawnAnswerRequest(BaseModel):
    repo_path: str
    question: str
    answer: str

class ThrawnAskRequest(BaseModel):
    repo_path: str
    question: str

class ThrawnArchitectureRequest(BaseModel):
    repo_path: str
    pattern: str

class RepoRequest(BaseModel):
    repo_path: str

class ObjectiveRequest(BaseModel):
    repo_path: str
    goal: str
    success_criteria: Optional[List[str]] = None
    constraints: Optional[List[str]] = None

class ObjectiveTransitionRequest(BaseModel):
    repo_path: str
    phase: str
    active_task_id: Optional[str] = None
    last_agent_id: Optional[str] = None
    last_result: Optional[Dict[str, Any]] = None
    blocked_reason: Optional[str] = None

class ObjectiveControlRequest(BaseModel):
    repo_path: str

# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@app.get("/health")
def healthcheck():
    return {"status": "ok"}

@app.get("/repos")
def get_repos():
    orchestrator.load_config()
    root_path = os.path.abspath(os.path.dirname(os.path.dirname(__file__)))
    if sync_discovered_repositories(orchestrator.priority_config, root_path):
        orchestrator.save_config()
    repositories = []
    for repo in orchestrator.priority_config.get("repositories", []):
        hydrated = dict(repo)
        repo_path = hydrated.get("repo_path", "")
        fleet_state = StateManager(repo_path).read_fleet_state() if repo_path else {}
        if fleet_state.get("status") == "blocked":
            hydrated["agent_status"] = "blocked"
            hydrated["status_detail"] = fleet_state.get("output_summary", "Fleet state is blocked.")
            hydrated["blocker_type"] = fleet_state.get("blocker_type")
        repositories.append(hydrated)
    return sorted(
        repositories,
        key=lambda repo: (repo.get("priority", 999), os.path.basename(repo.get("repo_path", "")).lower()),
    )

@app.post("/repos/register")
def register_repo(req: RepoRequest):
    orchestrator.load_config()
    try:
        repo, added = register_repository(orchestrator.priority_config, req.repo_path)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    if added:
        orchestrator.save_config()
        orchestrator.load_config()

    return {"status": "added" if added else "exists", "repo": repo}

@app.get("/agents")
def get_agents():
    return [
        {
            "id": k, 
            "name": v["class"], 
            "wake_word": v["wake_word"], 
            "tools": [ToolRegistry.get_tool(t_id) | {"id": t_id} for t_id in v["tools"]]
        }
        for k, v in AGENT_REGISTRY.items()
    ]

# --- Task 1: Async /run-task ---

@app.post("/run-task")
def run_task(req: RunTaskRequest):
    """Submit an agent task asynchronously. Returns a session_id for polling."""
    # 1. Write the active prompt
    exegol_dir = os.path.join(req.repo_path, ".exegol")
    os.makedirs(exegol_dir, exist_ok=True)
    prompt_file = os.path.join(exegol_dir, "active_prompt.md")

    with open(prompt_file, "w", encoding="utf-8") as f:
        f.write(req.task_prompt)

    # 2. Create a tracking entry
    session_id = uuid.uuid4().hex[:12]
    _running_tasks[session_id] = {
        "session_id": session_id,
        "agent_id": req.agent_id,
        "repo_path": req.repo_path,
        "status": "queued",
        "result": None,
        "started_at": datetime.datetime.now().isoformat(),
        "finished_at": None,
    }

    # 3. Submit to thread pool — non-blocking
    _executor.submit(_execute_agent_sync, session_id, req.repo_path, req.agent_id, req.model)

    return {"session_id": session_id, "status": "queued"}


@app.get("/task-status/{session_id}")
def get_task_status(session_id: str):
    """Poll for the result of an async /run-task submission."""
    entry = _running_tasks.get(session_id)
    if not entry:
        raise HTTPException(status_code=404, detail="Session not found.")
    return entry

# --- Epic 1: Human Action Queue (HITL) ---

@app.get("/human-queue")
def get_human_queue(repo_path: str):
    hm = HITLManager(repo_path)
    return hm.get_queue()

@app.post("/human-queue/action")
def update_human_queue(req: ActionQueueRequest):
    hm = HITLManager(req.repo_path)
    
    if req.action == "dismiss":
        queue = hm.get_queue()
        queue = [item for item in queue if item.get("id") != req.item_id]
        hm.sm.write_json(hm.queue_file, queue)
        hm._sync_to_markdown(queue)
        return {"status": "success"}
    
    status = "done" if req.action == "done" else "pending"
    if hm.resolve_task(req.item_id, status=status, notes=req.notes):
        return {"status": "success"}

    raise HTTPException(status_code=404, detail="Item not found")

# --- Epic 2: Backlog Management ---

@app.get("/backlog")
def get_backlog(repo_path: str):
    return BacklogManager(repo_path).load_backlog()

@app.post("/backlog/update")
def update_backlog(req: BacklogUpdateRequest):
    if BacklogManager(req.repo_path).update_task(req.task_id, req.updates):
        return {"status": "success"}
    raise HTTPException(status_code=404, detail="Task not found")

@app.post("/backlog/add")
def add_to_backlog(req: Dict[str, Any]):
    repo_path = req.get("repo_path")
    task_summary = req.get("summary")
    if not repo_path or not task_summary:
        raise HTTPException(status_code=400, detail="Missing repo_path or summary")

    new_task = {
        "id": f"user_task_{uuid.uuid4().hex[:8]}",
        "summary": task_summary,
        "priority": req.get("priority", "medium"),
        "status": "todo",
        "target_agent": "developer_dex",
        "source": "ui",
        "created_at": datetime.datetime.now().isoformat(),
    }

    BacklogManager(repo_path).add_task(new_task)

    # Notify Slack (Interaction Layer Sync)
    try:
        from tools.slack_tool import post_backlog_update
        post_backlog_update(task_summary, new_task["priority"], new_task["target_agent"])
    except Exception as e:
        print(f"[API] Failed to notify Slack of backlog update: {e}")

    return {"status": "success", "task": new_task}

@app.post("/backlog/reorder")
def reorder_backlog(req: Dict[str, Any]):
    repo_path = req.get("repo_path")
    new_order_ids = req.get("task_ids")
    if not repo_path or not new_order_ids:
        raise HTTPException(status_code=400, detail="Missing repo_path or task_ids")

    if not BacklogManager(repo_path).save_backlog_order(new_order_ids):
        raise HTTPException(status_code=400, detail="No task_ids provided.")
    return {"status": "success"}

@app.post("/backlog/groom")
def groom_backlog(req: Dict[str, Any]):
    repo_path = req.get("repo_path")
    if not repo_path:
        raise HTTPException(status_code=400, detail="Missing repo_path")

    manager = BacklogManager(repo_path)
    archived_completed = manager.archive_completed_tasks()
    dedupe = manager.dedupe_auto_failures()
    return {
        "status": "success",
        "archived_completed": archived_completed,
        **dedupe,
        "remaining_active": len(manager.load_backlog()),
    }

# --- Epic 3: Agent Settings & Model Routing ---

@app.get("/agent-models")
def get_agent_models():
    root_path = os.path.dirname(os.path.dirname(__file__))
    sm = StateManager(root_path)
    return sm.read_json("config/agent_models.json") or {}

@app.post("/agent-models")
def update_agent_models(req: AgentModelsRequest):
    root_path = os.path.dirname(os.path.dirname(__file__))
    sm = StateManager(root_path)

    current_mappings = sm.read_json("config/agent_models.json") or {}
    for mapping in req.mappings:
        current_mappings[mapping.agent_id] = mapping.model

    sm.write_json("config/agent_models.json", current_mappings)
    return {"status": "success"}

@app.get("/local-models")
def get_local_models():
    """Fetches available models from Ollama for selection in the UI."""
    try:
        # Try to get Ollama base URL from env
        ollama_gen_url = os.getenv("OLLAMA_URL", "http://localhost:11434/api/generate")
        parsed = urlparse(ollama_gen_url)
        base_url = f"{parsed.scheme}://{parsed.netloc}"
        tags_url = f"{base_url}/api/tags"

        print(f"[API] Fetching local models from {tags_url}...")
        EgressFilter.validate_request(tags_url)
        
        response = requests.get(tags_url, timeout=5)
        if response.status_code == 200:
            data = response.json()
            models = data.get("models", [])
            print(f"[API] Found {len(models)} local models.")
            return models
        else:
            print(f"[API] Ollama /api/tags returned {response.status_code}")
            return []
    except Exception as e:
        print(f"[API] Error fetching local models: {e}")
        return []

@app.get("/api-keys/status")
def get_api_keys_status():
    """Checks for the presence of cloud API keys in the environment."""
    gemini_key = os.getenv("GEMINI_API_KEY")
    claude_key = os.getenv("ANTHROPIC_API_KEY")
    
    return {
        "gemini": bool(gemini_key and "your_gemini_key_here" not in gemini_key),
        "claude": bool(claude_key and "your_anthropic_key_here" not in claude_key),
    }

@app.get("/snapshots/{snapshot_name}")
def get_snapshot(snapshot_name: str, repo_path: str):
    snapshot_path = os.path.join(repo_path, ".exegol", "eval_reports", "snapshots", f"{snapshot_name}.json")
    if not os.path.exists(snapshot_path):
        raise HTTPException(status_code=404, detail="Snapshot not found.")

    with open(snapshot_path, "r", encoding="utf-8") as f:
        return json.load(f)

# --- Epic 4: Thrawn Interaction ---

@app.get("/thrawn/intel")
def get_thrawn_intel(repo_path: str):
    mgr = ThrawnIntelManager(repo_path)
    return mgr.read_intent()

@app.post("/thrawn/objective")
def update_thrawn_objective(req: ThrawnObjectiveRequest):
    mgr = ThrawnIntelManager(req.repo_path)
    mgr.update_objective(req.objective)
    return {"status": "success"}

@app.post("/thrawn/answer")
def answer_thrawn_question(req: ThrawnAnswerRequest):
    mgr = ThrawnIntelManager(req.repo_path)
    mgr.answer_question(req.question, req.answer)
    try:
        from tools.hitl_manager import HITLManager
        hitl_mgr = HITLManager(req.repo_path)
        pending = hitl_mgr.get_pending()
        for task in pending:
            context = task.get("context", "")
            task_title = task.get("task", "")
            is_match = False
            if req.question in context:
                is_match = True
            elif task_title.startswith("Thrawn: ") and req.question.startswith(task_title[8:].rstrip(".")):
                is_match = True
            if is_match:
                hitl_mgr.resolve_task(
                    item_id=task.get("id"),
                    status="done",
                    notes=f"Answered via Workbench: {req.answer[:100]}"
                )
    except Exception as e:
        print(f"[API] Failed to auto-resolve HITL task: {e}")
    return {"status": "success"}

@app.post("/thrawn/ask")
def ask_thrawn_question(req: ThrawnAskRequest):
    mgr = ThrawnIntelManager(req.repo_path)
    intel = mgr.read_intent()
    intel["questions"].append({"question": req.question, "answer": None})
    mgr.save_intent(intel)
    return {"status": "success"}

@app.post("/thrawn/architecture")
def add_thrawn_architecture(req: ThrawnArchitectureRequest):
    mgr = ThrawnIntelManager(req.repo_path)
    mgr.add_architecture(req.pattern)
    return {"status": "success"}

@app.get("/poe/roadmap")
def get_poe_roadmap(repo_path: str):
    return load_or_build_poe_roadmap_brief(repo_path)

# --- Epic 5: Fleet Health Dashboard ---

@app.get("/fleet/metrics")
def get_fleet_metrics(
    repo_path: str,
    days: int = 30,
    start_date: Optional[str] = DEFAULT_METRICS_START_DATE,
):
    mgr = SuccessMetricsManager(repo_path)
    enable_live_judge = os.getenv("EXEGOL_METRICS_ENABLE_LIVE_JUDGE", "").lower() in {"1", "true", "yes"}
    try:
        return mgr.calculate_metrics(
            days=days,
            enable_live_judge=enable_live_judge,
            start_date=start_date,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

@app.get("/costs")
def get_costs(repo_path: str, days: int = 30):
    """Fetch estimated cost analysis from local interaction logs."""
    from tools.cost_analyzer import get_cost_report
    return get_cost_report(repo_path, days=days)

@app.get("/fleet/interactions")
def get_fleet_interactions(
    repo_path: str, 
    agent_id: Optional[str] = None, 
    outcome: Optional[str] = None, 
    days: int = 30,
    start_date: Optional[str] = None,
):
    """Fetches detailed interaction logs for drill-down analysis."""
    try:
        period_start = parse_metrics_start_date(start_date)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    logs = filter_logs_since(
        read_interaction_logs(
            [repo_path],
            days=calculate_read_days_for_start(period_start, days),
        ),
        period_start,
    )
    
    # Filtering
    if agent_id:
        normalized_agent_id = _normalize_registry_agent_id(agent_id)
        logs = [
            l
            for l in logs
            if _normalize_registry_agent_id(l.get("agent_id")) == normalized_agent_id
        ]
    if outcome:
        logs = [l for l in logs if l.get("outcome") == outcome]
        
    # Sort by timestamp descending
    logs.sort(key=lambda x: x.get("timestamp", ""), reverse=True)
    return logs

@app.get("/fleet/health")
def get_fleet_health():
    """Aggregates health metrics across all managed repositories."""
    orchestrator.load_config()
    repos = orchestrator.priority_config.get("repositories", [])
    health_data = []

    for repo in repos:
        path = repo.get("repo_path")
        sm = StateManager(path)
        
        # 1. Backlog size (uncompleted tasks)
        backlog = sm.read_json(".exegol/backlog.json") or []
        backlog_count = len([t for t in backlog if t.get("status") in ["todo", "pending_prioritization", "backlogged"]])
        
        # 2. HITL size (User action required)
        hitl = sm.read_json(".exegol/user_action_required.json") or []
        hitl_count = len([t for t in hitl if t.get("status") != "done"])
        
        # 3. Aggregated Metrics
        from tools.fleet_logger import read_interaction_logs
        logs = read_interaction_logs([path], days=30)
        
        total_tasks = len(logs)
        successes = len([l for l in logs if l.get("outcome") == "success"])
        avg_steps = sum([l.get("steps_used", 0) for l in logs]) / total_tasks if total_tasks > 0 else 0
        success_rate = (successes / total_tasks) * 100 if total_tasks > 0 else 0
        
        last_log = logs[-1] if logs else None
        
        health_data.append({
            "name": os.path.basename(path),
            "path": path,
            "status": repo.get("agent_status", "idle"),
            "priority": repo.get("priority", 10),
            "backlog_count": backlog_count,
            "hitl_count": hitl_count,
            "success_rate": round(success_rate, 1),
            "avg_steps": round(avg_steps, 1),
            "total_tasks": total_tasks,
            "last_activity": last_log.get("timestamp") if last_log else None,
            "last_agent": last_log.get("agent_id") if last_log else None,
            "last_outcome": last_log.get("outcome") if last_log else None
        })

    return health_data

@app.get("/objective")
def get_objective(repo_path: str):
    return ObjectiveManager(repo_path).load()

@app.post("/objective")
def set_objective(req: ObjectiveRequest):
    if not req.goal.strip():
        raise HTTPException(status_code=400, detail="Objective goal is required")
    return ObjectiveManager(req.repo_path).create_or_update(
        goal=req.goal,
        success_criteria=req.success_criteria,
        constraints=req.constraints,
    )

@app.post("/objective/transition")
def transition_objective(req: ObjectiveTransitionRequest):
    try:
        return ObjectiveManager(req.repo_path).transition(
            phase=req.phase,
            active_task_id=req.active_task_id,
            last_agent_id=req.last_agent_id,
            last_result=req.last_result,
            blocked_reason=req.blocked_reason,
        )
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc))

@app.post("/objective/start")
def start_objective_loop(req: ObjectiveControlRequest):
    repo_path = os.path.abspath(req.repo_path)
    manager = ObjectiveManager(repo_path)
    objective = manager.load()
    if not str(objective.get("goal") or "").strip():
        raise HTTPException(status_code=400, detail="Cannot start: no objective goal is set.")

    with _objective_loops_lock:
        if repo_path in _active_objective_loops:
            event = _active_objective_loops[repo_path]["event"]
            thread = _active_objective_loops[repo_path]["thread"]
            if thread.is_alive():
                if objective.get("status") == "paused":
                    manager.resume()
                return {"status": "success", "detail": "Loop already running.", "objective": manager.load()}

        stop_event = threading.Event()
        if objective.get("status") == "paused":
            manager.resume()
        
        thread = threading.Thread(
            target=_objective_loop_for_repo,
            args=(repo_path, stop_event),
            daemon=True
        )
        _active_objective_loops[repo_path] = {
            "event": stop_event,
            "thread": thread,
            "started_at": datetime.datetime.now().isoformat()
        }
        thread.start()

    return {"status": "success", "detail": "Loop started.", "objective": manager.load()}

@app.post("/objective/pause")
def pause_objective(req: ObjectiveControlRequest):
    repo_path = os.path.abspath(req.repo_path)
    manager = ObjectiveManager(repo_path)
    try:
        objective = manager.pause()
        return {"status": "success", "detail": "Objective paused.", "objective": objective}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

@app.post("/objective/resume")
def resume_objective(req: ObjectiveControlRequest):
    repo_path = os.path.abspath(req.repo_path)
    manager = ObjectiveManager(repo_path)
    try:
        manager.resume()
        with _objective_loops_lock:
            thread_running = False
            if repo_path in _active_objective_loops:
                if _active_objective_loops[repo_path]["thread"].is_alive():
                    thread_running = True
            if not thread_running:
                stop_event = threading.Event()
                thread = threading.Thread(
                    target=_objective_loop_for_repo,
                    args=(repo_path, stop_event),
                    daemon=True
                )
                _active_objective_loops[repo_path] = {
                    "event": stop_event,
                    "thread": thread,
                    "started_at": datetime.datetime.now().isoformat()
                }
                thread.start()
        return {"status": "success", "detail": "Objective resumed.", "objective": manager.load()}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

@app.post("/objective/stop")
def stop_objective_loop(req: ObjectiveControlRequest):
    repo_path = os.path.abspath(req.repo_path)
    manager = ObjectiveManager(repo_path)
    objective = manager.load()
    phase = objective.get("phase", "idle")
    if phase != "idle":
        try:
            manager.transition("idle")
        except Exception as e:
            print(f"[API] Failed to transition to idle: {e}")

    with _objective_loops_lock:
        if repo_path in _active_objective_loops:
            _active_objective_loops[repo_path]["event"].set()
            _active_objective_loops.pop(repo_path)
            return {"status": "success", "detail": "Loop stopped and objective reset to idle."}
        
    return {"status": "success", "detail": "Loop was not running, objective reset to idle."}

@app.get("/objective/status")
def get_objective_status(repo_path: str):
    repo_path = os.path.abspath(repo_path)
    manager = ObjectiveManager(repo_path)
    objective = manager.load()
    
    thread_alive = False
    started_at = None
    with _objective_loops_lock:
        if repo_path in _active_objective_loops:
            thread_alive = _active_objective_loops[repo_path]["thread"].is_alive()
            started_at = _active_objective_loops[repo_path]["started_at"]
            
    return {
        "objective": objective,
        "loop_running": thread_alive,
        "loop_started_at": started_at
    }

@app.get("/fleet/tools")
def get_fleet_tools(repo_path: str):
    """Returns the comprehensive tool registry with usage statistics."""
    from tools.fleet_logger import read_interaction_logs
    from agents.registry import AGENT_REGISTRY
    
    logs = read_interaction_logs([repo_path], days=30)
    tool_usage = {}
    
    # 1. Map agents to tools
    agent_tools = {k: v["tools"] for k, v in AGENT_REGISTRY.items()}
    
    # 2. Count tool usage from logs (if logged)
    # Note: Currently tools are not explicitly logged in interaction_logs.
    # We can infer usage from agent logs for now.
    for log in logs:
        agent_id = log.get("agent_id")
        if agent_id in agent_tools:
            for t_id in agent_tools[agent_id]:
                tool_usage[t_id] = tool_usage.get(t_id, 0) + 1

    registry = ToolRegistry.get_all_tools()
    result = []
    for t_id, info in registry.items():
        # Find which agents have this tool
        owners = [a_id for a_id, tools in agent_tools.items() if t_id in tools]
        
        result.append({
            "id": t_id,
            "description": info["description"],
            "risk": info["risk"],
            "category": info["category"],
            "agents": owners,
            "usage_count": tool_usage.get(t_id, 0)
        })
    
    return result

# --- Epic 6: Evaluation Reports ---

@app.get("/evaluations")
def get_evaluations(repo_path: str):
    """Fetch a list of all evaluation reports."""
    eval_dir = os.path.join(repo_path, ".exegol", "eval_reports")
    if not os.path.exists(eval_dir):
        return []
        
    reports = []
    for f in os.listdir(eval_dir):
        if f.endswith(".json") and not os.path.isdir(os.path.join(eval_dir, f)):
            reports.append(f)
            
    # Sort descending by name (which includes date)
    reports.sort(reverse=True)
    return reports

@app.get("/evaluations/{filename}")
def get_evaluation_report(filename: str, repo_path: str):
    """Fetch a specific evaluation report."""
    report_path = os.path.join(repo_path, ".exegol", "eval_reports", filename)
    if not os.path.exists(report_path):
        raise HTTPException(status_code=404, detail="Evaluation report not found.")

    with open(report_path, "r", encoding="utf-8") as f:
        return json.load(f)

# --- Epic 8: MCP & Error Handling ---

@app.post("/fatal-error")
def handle_fatal_error(req: Dict[str, Any]):
    """
    Handles terminal errors marked as 'FATAL'. 
    Routes them to the backlog for immediate developer attention.
    """
    repo_path = req.get("repo_path")
    error_message = req.get("error_message")
    context = req.get("context", "")

    if not repo_path or not error_message:
        raise HTTPException(status_code=400, detail="Missing repo_path or error_message")

    sm = StateManager(repo_path)
    backlog = sm.read_json(".exegol/backlog.json") or []

    new_task = {
        "id": f"fatal_{uuid.uuid4().hex[:6]}",
        "summary": f"🚨 FATAL ERROR: {error_message}",
        "description": f"Context: {context}",
        "priority": "critical",
        "status": "todo",
        "target_agent": "developer_dex",
        "source": "antigravity_mcp",
        "created_at": datetime.datetime.now().isoformat(),
    }

    backlog.insert(0, new_task) # Priority at the top
    sm.write_json(".exegol/backlog.json", backlog)
    
    return {"status": "success", "task_id": new_task["id"]}


# --- Epic 10: Model Benchmark Database ---

@app.get("/models/benchmarks")
def get_model_benchmarks(repo_path: str, category: Optional[str] = None):
    """Returns the full model benchmark table, optionally filtered by category."""
    from tools.model_benchmark_db import get_all_models
    return get_all_models(repo_path, category=category)

@app.post("/models/compare")
def compare_model_benchmarks(req: ModelCompareRequest):
    """Compare selected models side-by-side with factor-by-factor winners."""
    from tools.model_benchmark_db import compare_models
    return compare_models(req.repo_path, req.model_names)

@app.get("/models/recommend")
def recommend_model(repo_path: str, role: str = "general"):
    """Recommend top 5 models for a given agent role (coding, research, writing, ops, creative)."""
    from tools.model_benchmark_db import recommend_for_role
    return recommend_for_role(repo_path, role)

@app.get("/models/ollama")
def get_ollama_benchmarks(repo_path: str):
    """Returns only models available on Ollama, sorted by coding score."""
    from tools.model_benchmark_db import get_ollama_models
    return get_ollama_models(repo_path)

@app.get("/models/search")
def search_model_benchmarks(repo_path: str, q: str):
    """Search models by name, provider, or notes."""
    from tools.model_benchmark_db import search_models
    return search_models(repo_path, q)


# --- Epic 9: Secrets & API Key Rotation ---

@app.get("/secrets/status")
def get_secrets_status(repo_path: str):
    """Full audit of all managed API keys — health, age, rotation status."""
    from tools.secret_manager import SecretManager
    sm = SecretManager(repo_path)
    return sm.get_status_summary()

@app.post("/secrets/rotate")
def rotate_secret(req: SecretRotateRequest):
    """Rotate a single API key from the Workbench UI."""
    from tools.secret_manager import SecretManager
    sm = SecretManager(req.repo_path)
    result = sm.rotate_key(req.env_var, req.new_value, rotated_by="workbench_ui")
    if result["status"] == "error":
        raise HTTPException(status_code=400, detail=result["detail"])
    return result

@app.post("/secrets/audit")
def audit_secrets(req: Dict[str, Any]):
    """Trigger a full key health audit and escalate unhealthy keys to HITL."""
    repo_path = req.get("repo_path")
    if not repo_path:
        raise HTTPException(status_code=400, detail="Missing repo_path")
    from tools.secret_manager import SecretManager
    sm = SecretManager(repo_path)
    escalated = sm.escalate_unhealthy_keys()
    return {"status": "success", "escalated_count": len(escalated), "task_ids": escalated}


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)
