import os
import json
from tools.snapshot_tester import capture_snapshot, compare_snapshots

def run_regression_eval(agent_output: dict, snapshot_name: str):
    """Orchestrates a snapshot comparison for a given agent output.
    
    If no baseline exists, it treats the current output as the new baseline.
    If a baseline exists, it compares and returns the result.
    """
    print(f"[Eval] Running snapshot regression for: {snapshot_name}")
    
    result = compare_snapshots(agent_output, snapshot_name)
    
    if result["result"] == "missing":
        print(f"[Eval] No baseline found for {snapshot_name}. Capturing first snapshot.")
        h = capture_snapshot(agent_output, snapshot_name)
        return {"status": "baseline_captured", "hash": h}
    
    if result["result"] == "match":
        print(f"[Eval] PASS: {snapshot_name} matches baseline.")
        return {"status": "pass"}
    
    if result["result"] == "mismatch":
        print(f"[Eval] FAIL: {snapshot_name} differs from baseline!")
        return {
            "status": "fail",
            "saved": result.get("saved_hash"),
            "current": result.get("current_hash")
        }
