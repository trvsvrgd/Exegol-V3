import os
import json
import uuid
import datetime
import uvicorn
import requests
from urllib.parse import urlparse
from concurrent.futures import ThreadPoolExecutor
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
from tools.tool_registry import ToolRegistry
from tools.hitl_manager import HITLManager

# ---------------------------------------------------------------------------
# App Setup
# ---------------------------------------------------------------------------

app = FastAPI(title="Exegol V3 - Control Tower Backend")

# Enable CORS for Control Tower UI
ALLOWED_ORIGINS = [
    "http://localhost:3000",
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
_PUBLIC_PATHS = {"/", "/docs", "/openapi.json", "/redoc"}

API_KEY = os.getenv("EXEGOL_API_KEY", "dev-local-key")


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

# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@app.get("/repos")
def get_repos():
    orchestrator.load_config()
    return orchestrator.priority_config.get("repositories", [])

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
    sm = StateManager(repo_path)
    return sm.read_json(".exegol/backlog.json") or []

@app.post("/backlog/update")
def update_backlog(req: BacklogUpdateRequest):
    sm = StateManager(req.repo_path)
    if sm.update_backlog_task(req.task_id, req.updates):
        return {"status": "success"}
    raise HTTPException(status_code=404, detail="Task not found")

@app.post("/backlog/add")
def add_to_backlog(req: Dict[str, Any]):
    repo_path = req.get("repo_path")
    task_summary = req.get("summary")
    if not repo_path or not task_summary:
        raise HTTPException(status_code=400, detail="Missing repo_path or summary")

    sm = StateManager(repo_path)
    backlog = sm.read_json(".exegol/backlog.json") or []

    new_task = {
        "id": f"user_task_{uuid.uuid4().hex[:8]}",
        "summary": task_summary,
        "priority": req.get("priority", "medium"),
        "status": "todo",
        "target_agent": "developer_dex",
        "source": "ui",
        "created_at": datetime.datetime.now().isoformat(),
    }

    backlog.append(new_task)
    sm.write_json(".exegol/backlog.json", backlog)

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

    sm = StateManager(repo_path)
    backlog = sm.read_json(".exegol/backlog.json") or []

    task_map = {t["id"]: t for t in backlog}
    reordered_backlog = [task_map[tid] for tid in new_order_ids if tid in task_map]

    ordered_ids = set(new_order_ids)
    for t in backlog:
        if t["id"] not in ordered_ids:
            reordered_backlog.append(t)

    sm.write_json(".exegol/backlog.json", reordered_backlog)
    return {"status": "success"}

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

# --- Epic 5: Fleet Health Dashboard ---

@app.get("/fleet/metrics")
def get_fleet_metrics(repo_path: str):
    from tools.metrics_manager import SuccessMetricsManager
    mgr = SuccessMetricsManager(repo_path)
    return mgr.calculate_metrics()

@app.get("/costs")
def get_costs(repo_path: str, days: int = 30):
    """Fetches real cost analysis via CostAnalyzer."""
    from tools.cost_analyzer import get_cost_report
    return get_cost_report(repo_path, days=days)

@app.get("/fleet/interactions")
def get_fleet_interactions(
    repo_path: str, 
    agent_id: Optional[str] = None, 
    outcome: Optional[str] = None, 
    days: int = 30
):
    """Fetches detailed interaction logs for drill-down analysis."""
    logs = read_interaction_logs([repo_path], days=days)
    
    # Filtering
    if agent_id:
        logs = [l for l in logs if l.get("agent_id") == agent_id]
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
