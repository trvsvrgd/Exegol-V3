import os
import json
import uvicorn
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import List, Optional

from orchestrator import ExegolOrchestrator
from agents.registry import AGENT_REGISTRY

app = FastAPI(title="Exegol V3 - Backend Bridge")

# Enable CORS for Next.js development
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

orchestrator = ExegolOrchestrator()

class RunTaskRequest(BaseModel):
    repo_path: str
    agent_id: str
    model: str
    task_prompt: str

@app.get("/repos")
async def get_repos():
    orchestrator.load_config()
    return orchestrator.priority_config.get("repositories", [])

@app.get("/agents")
async def get_agents():
    return [
        {"id": k, "name": v["class"], "wake_word": v["wake_word"], "tools": v["tools"]}
        for k, v in AGENT_REGISTRY.items()
    ]

@app.post("/run-task")
async def run_task(req: RunTaskRequest):
    # 1. Update the active prompt file
    exegol_dir = os.path.join(req.repo_path, ".exegol")
    os.makedirs(exegol_dir, exist_ok=True)
    prompt_file = os.path.join(exegol_dir, "active_prompt.md")
    
    with open(prompt_file, "w", encoding="utf-8") as f:
        f.write(req.task_prompt)
    
    # 2. Trigger the agent via Orchestrator
    # We pass the routing preference and agent_id explicitly
    result = orchestrator.wake_and_execute_agent(
        repo_info={"repo_path": req.repo_path},
        routing=req.model,
        max_steps=20,
        agent_id=req.agent_id
    )
    
    if not result:
        raise HTTPException(status_code=500, detail="Agent execution failed.")
    
    return result.to_dict()

@app.get("/snapshots/{snapshot_name}")
async def get_snapshot(snapshot_name: str, repo_path: str):
    snapshot_path = os.path.join(repo_path, ".exegol", "eval_reports", "snapshots", f"{snapshot_name}.json")
    if not os.path.exists(snapshot_path):
        raise HTTPException(status_code=404, detail="Snapshot not found.")
    
    with open(snapshot_path, "r", encoding="utf-8") as f:
        return json.load(f)

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)
