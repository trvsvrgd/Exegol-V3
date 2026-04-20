import sys
import os
import json
import shutil
from unittest.mock import MagicMock

# Add src to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'src')))

from session_manager import SessionManager
from handoff import HandoffContext
from agents.registry import AGENT_REGISTRY

# --- SETUP ---
REPO_PATH = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
EXEGOL_DIR = os.path.join(REPO_PATH, ".exegol")
BACKLOG_FILE = os.path.join(EXEGOL_DIR, "backlog.json")
VIBE_FILE = os.path.join(EXEGOL_DIR, "vibe_todo.json")
SNAPSHOT_DIR = os.path.join(EXEGOL_DIR, "eval_reports", "snapshots")

def setup_dummy_backlog():
    os.makedirs(EXEGOL_DIR, exist_ok=True)
    backlog = [
        {
            "id": "verify_task_001",
            "summary": "Implement a test file for verification",
            "priority": "high",
            "status": "todo"
        }
    ]
    with open(BACKLOG_FILE, 'w') as f:
        json.dump(backlog, f, indent=4)
    
    if os.path.exists(VIBE_FILE):
        os.remove(VIBE_FILE)

def cleanup():
    # Keep the logs but maybe clear snapshots for a fresh run
    if os.path.exists(SNAPSHOT_DIR):
        shutil.rmtree(SNAPSHOT_DIR)

# --- MOCKING ---
from inference.llm_client import LLMClient
# Mocking LLM to return a simple coding plan
LLMClient.generate = MagicMock(side_effect=[
    # Response for ProductPoe (Prompt enrichment)
    "# Active Developer Task\n\n**Task ID:** verify_task_001\n\nDetailed instructions...",
    # Response for DeveloperDex (Planning)
    json.dumps([{"type": "write", "path": "verify_test.txt", "content": "Hello Verification"}])
])
LLMClient.parse_json_response = MagicMock(return_value=[{"type": "write", "path": "verify_test.txt", "content": "Hello Verification"}])

# --- EXECUTION ---

def run_verification():
    sm = SessionManager(log_every_session=True)
    
    print("\n--- Phase 1: ProductPoe selects task ---")
    handoff_poe = HandoffContext(repo_path=REPO_PATH, agent_id="product_poe", task_id="verify", model_routing="ollama", max_steps=10)
    res_poe = sm.spawn_agent_session("product_poe", AGENT_REGISTRY["product_poe"]["module"], AGENT_REGISTRY["product_poe"]["class"], handoff_poe)
    print(f"Poe Result: {res_poe.output_summary}")
    print(f"Next Agent: {res_poe.next_agent_id}")
    
    print("\n--- Phase 2: DeveloperDex implements task and captures snapshot ---")
    handoff_dex = HandoffContext(repo_path=REPO_PATH, agent_id="developer_dex", task_id="verify_task_001", model_routing="ollama", max_steps=20)
    res_dex = sm.spawn_agent_session("developer_dex", AGENT_REGISTRY["developer_dex"]["module"], AGENT_REGISTRY["developer_dex"]["class"], handoff_dex)
    print(f"Dex Result: {res_dex.output_summary}")
    print(f"Snapshot Hash: {res_dex.snapshot_hash}")
    
    print("\n--- Phase 3: QualityQuigon validates snapshot (Baseline Capture) ---")
    handoff_quigon = HandoffContext(repo_path=REPO_PATH, agent_id="quality_quigon", task_id="verify_task_001", model_routing="ollama", max_steps=15, snapshot_hash=res_dex.snapshot_hash)
    res_quigon = sm.spawn_agent_session("quality_quigon", AGENT_REGISTRY["quality_quigon"]["module"], AGENT_REGISTRY["quality_quigon"]["class"], handoff_quigon)
    print(f"Quigon Result: {res_quigon.output_summary}")

    print("\n--- Phase 4: QualityQuigon validates snapshot (Comparison - PASS) ---")
    # To pass, we need to provide the actual data that matches the baseline
    dex_output = {
        "task_id": "verify_task_001",
        "agent": "DeveloperDexAgent",
        "actions_performed": ["Write verify_test.txt: Success"]
    }
    # We'll mock compare_snapshots to return match for this run
    from tools import snapshot_tester
    snapshot_tester.compare_snapshots = MagicMock(return_value={"result": "match", "message": "Match"})
    
    res_quigon_2 = sm.spawn_agent_session("quality_quigon", AGENT_REGISTRY["quality_quigon"]["module"], AGENT_REGISTRY["quality_quigon"]["class"], handoff_quigon)
    print(f"Quigon Result 2: {res_quigon_2.output_summary}")
    print(f"Next Agent: {res_quigon_2.next_agent_id}")

    print("\n--- Phase 5: QualityQuigon detects mismatch (Self-Healing Loop) ---")
    # Mock compare_snapshots to return mismatch
    snapshot_tester.compare_snapshots = MagicMock(return_value={
        "result": "mismatch", 
        "message": "Mismatch detected", 
        "saved_hash": "old_hash", 
        "current_hash": "new_hash"
    })
    
    res_quigon_3 = sm.spawn_agent_session("quality_quigon", AGENT_REGISTRY["quality_quigon"]["module"], AGENT_REGISTRY["quality_quigon"]["class"], handoff_quigon)
    print(f"Quigon Result 3: {res_quigon_3.output_summary}")
    print(f"Next Agent (Should be developer_dex): {res_quigon_3.next_agent_id}")
    print(f"Regression Context: {res_quigon_3.regression_context}")

    assert res_quigon_3.next_agent_id == "developer_dex"
    assert "Mismatch detected" in res_quigon_3.regression_context

    # Cleanup the test file created by Dex
    test_file = os.path.join(REPO_PATH, "verify_test.txt")
    if os.path.exists(test_file):
        os.remove(test_file)

if __name__ == "__main__":
    setup_dummy_backlog()
    try:
        run_verification()
        print("\nPipeline verification successful!")
    except Exception as e:
        print(f"\nPipeline verification failed: {e}")
        import traceback
        traceback.print_exc()
    # cleanup()
