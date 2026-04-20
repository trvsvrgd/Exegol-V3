import os
import json
import hashlib

def capture_snapshot(data: dict, snapshot_name: str, snapshots_dir: str = ".exegol/eval_reports/snapshots") -> str:
    """Captures a JSON data snapshot and saves it to a file.
    
    Returns the hash of the snapshot.
    """
    os.makedirs(snapshots_dir, exist_ok=True)
    
    # Sort keys to ensure consistent hashing
    data_str = json.dumps(data, sort_keys=True, indent=2)
    data_hash = hashlib.sha256(data_str.encode()).hexdigest()
    
    snapshot_path = os.path.join(snapshots_dir, f"{snapshot_name}.json")
    with open(snapshot_path, 'w', encoding='utf-8') as f:
        f.write(data_str)
        
    return data_hash

def compare_snapshots(data: dict, snapshot_name: str, snapshots_dir: str = ".exegol/eval_reports/snapshots") -> dict:
    """Compares current data against a saved snapshot.
    
    Returns a result dict with 'match', 'diff', or 'missing'.
    """
    snapshot_path = os.path.join(snapshots_dir, f"{snapshot_name}.json")
    if not os.path.exists(snapshot_path):
        return {"result": "missing", "message": f"Snapshot {snapshot_name} not found."}
        
    with open(snapshot_path, 'r', encoding='utf-8') as f:
        saved_data = json.load(f)
        
    if data == saved_data:
        return {"result": "match", "message": "Snapshots match exactly."}
    else:
        # Simple diffing logic - in a real implementation we might use a library
        return {
            "result": "mismatch",
            "message": "Snapshots do not match.",
            "saved_hash": hashlib.sha256(json.dumps(saved_data, sort_keys=True).encode()).hexdigest(),
            "current_hash": hashlib.sha256(json.dumps(data, sort_keys=True).encode()).hexdigest()
        }
