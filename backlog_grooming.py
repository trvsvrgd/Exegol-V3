import sqlite3
import os
import sys

# Ensure src/ is in the import path
sys.path.append(os.path.join(os.path.dirname(__file__), "src"))
from tools.backlog_manager import BacklogManager

import json
from config.app_definition_schema import validate_schema
def groom_backlog(execute: bool = False):
    db_path = os.path.join(".exegol", "backlog.db")
    if not os.path.exists(db_path):
        print(f"Error: Database not found at {db_path}")
        return

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    # Get all tasks
    cursor.execute("SELECT id, summary, priority, type, status, source_agent, archived_at FROM tasks")
    rows = cursor.fetchall()

    to_delete = []
    to_keep = []

    for row in rows:
        tid, summary, priority, ttype, status, source_agent, archived_at = row
        try:
            task_data = json.loads(row[5])
            validate_schema(task_data)
            # Add task processing logic here
            to_keep.append({"id": tid, "summary": summary, "priority": priority, "type": ttype, "status": status, "source_agent": source_agent, "archived_at": archived_at})
        except (json.JSONDecodeError, ValidationError) as e:
            print(f'Task validation error for {tid}: {e}')
            to_delete.append((tid, summary))

    print(f"Total tasks in database: {len(rows)}")
    print(f"Tasks identified for removal: {len(to_delete)}")
    print(f"Tasks to keep: {len(to_keep)}")

    if not execute:
        print("\n--- DRY RUN: Tasks that will be KEPT and ORGANIZED ---")
        for idx, task in enumerate(to_keep):
            print(f'  [KEEP] Rank {idx}: ID={task["id"]} | Summary={task["summary"]}')
        print("\nTo apply these changes, run with the execute flag: python backlog_grooming.py --execute")
        conn.close()
        return

    # Delete junk tasks
    print("\nExecuting database cleanup...")
    delete_query = "DELETE FROM tasks WHERE id = ?"
    for tid, _ in to_delete:
        cursor.execute(delete_query, (tid,))

    # Priority order for re-ranking the remaining actual tasks
    priority_order = [...]
    rank_map = {tid: idx for idx, tid in enumerate(priority_order)}
    for task in to_keep:
        tid = task["id"]
        rank = rank_map.get(tid, 999)
        archived_at = task["archived_at"]
        cursor.execute("UPDATE tasks SET rank = ?, archived_at = ? WHERE id = ?", (rank, archived_at, tid))

    conn.commit()
    conn.close()
    print("Database updates committed.")

    # Sync back to json files
    bm = BacklogManager(".")
    bm._sync_to_json()
    print("Grooming completed and synchronized successfully.")
    db_path = os.path.join(".exegol", "backlog.db")
    if not os.path.exists(db_path):
        print(f"Error: Database not found at {db_path}")
        return

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    # Get all tasks
    cursor.execute("SELECT id, summary, priority, type, status, source_agent, archived_at FROM tasks")
    rows = cursor.fetchall()
    
    to_delete = []
    to_keep = []

    # Expanded list of junk prefixes/patterns representing transient test run errors
    junk_patterns = [
        "auto_fail_", 
        "ops_intel_", 
        "slack_mock_", 
        "optimize_", 
        "dex_parse_fail_", 
        "ui_bug_fix_", 
        "mock_fix_", 
        "salvaged_loop_guard_",
        "slack_fail_",
        "crash_",
        "test_",
        "fix_gmail_integration_",
        "env_",
        "qa_fix_"
    ]

    for row in rows:
        tid, summary, priority, ttype, status, source_agent, archived_at = row
        
        is_junk = False
        # Check standard junk prefixes
        for pattern in junk_patterns:
            if tid.startswith(pattern):
                is_junk = True
                break
        
        # Check salvaged_hitl_ tasks
        if tid.startswith("salvaged_hitl_"):
            # Keep only specific intent questions/observations
            if tid in ["salvaged_hitl_242b8dd1", "salvaged_hitl_b4655abb"]:
                is_junk = False
            else:
                is_junk = True

        if is_junk:
            to_delete.append((tid, summary))
        else:
            to_keep.append({
                "id": tid,
                "summary": summary,
                "priority": priority,
                "type": ttype,
                "status": status,
                "source_agent": source_agent,
                "archived_at": archived_at
            })

    print(f"Total tasks in database: {len(rows)}")
    print(f"Tasks identified for removal: {len(to_delete)}")
    print(f"Tasks to keep: {len(to_keep)}")

    if not execute:
        print("\n--- DRY RUN: Tasks that will be KEPT and ORGANIZED ---")
        for idx, task in enumerate(to_keep):
            print(f"  [KEEP] Rank {idx}: ID={task['id']} | Summary={task['summary']}")
        
        print("\nTo apply these changes, run with the execute flag: python backlog_grooming.py --execute")
        conn.close()
        return

    # Delete junk tasks
    print("\nExecuting database cleanup...")
    delete_query = "DELETE FROM tasks WHERE id = ?"
    for tid, _ in to_delete:
        cursor.execute(delete_query, (tid,))
    
    # Priority order for re-ranking the remaining actual tasks
    # We will prioritize security first, followed by objective loop/architecture, dev/UI tasks, and observations.
    priority_order = [
        # 1. Critical & High Security Issues
        "sec_sec_arch_001",             # Missing Authentication & Authorization
        "sec_sec_zd_001",               # Prompt Injection Vector
        "sec_sec_zd_004",               # Hardcoded Secrets/Credentials in watcher
        "sec_sec_zd_006",               # SSRF Vector in api.py
        "sec_sec_zd_008",               # Missing Input Validation on LLM JSON Parse
        "sec_sec_ext_tool",             # Credentials key in credentials.json
        "sec_key_rotation_33c438",      # Secure key rotation lifecycle
        "sec_sec_arch_002",             # No Rate Limiting on Agent Invocations
        
        # 2. Objective Loop / Architecture Hardening (P0 / P1)
        "prod_supervisor_health_loop",  # Supervisor & health loop
        "arch_handoff_loop_guard",      # Handoff loop-depth guard
        "arch_handoff_hmac",            # HMAC signature on HandoffContext
        "arch_app_schema_validator",    # Schema validator implementation
        "arch_app_schema_enforcement",  # Schema enforcement in DeveloperDex
        "arch_api_auth_layer",          # API key auth middleware
        "arch_api_cors_hardening",      # Restrict API CORS
        "arch_hitl_queue_migration",    # Migrate HITL queue
        "improve_product_poe_metrics",  # Success criteria for ProductPoe
        
        # 3. Development / UI / Agents (P2)
        "dev_thrawn_autonomy_refactor", # Thrawn refactor
        "dev_fleet_dashboard_scaffolding", # Fleet dashboard UI
        "dev_scheduler_cadence",        # Finalize scheduler cadence
        "arch_vibe_vader_tools",        # Vibe Vader tools
        "arch_quigon_tools",            # Qui-Gon tools
        "arch_intel_ima_drive_sync",    # Drive sync for Intel Ima
        "agent_savant_sifo_implementation", # Savant Sifo agent
        "ui_success_metrics",           # Advanced Success Metrics UI
        "ui_cost_management",           # Cost & Quota Management UI
        "arch_finops_dashboard",        # FinOps cost tracking dashboard
        
        # 4. Human observations & clarifications
        "salvaged_hitl_b4655abb",       # Compliance Human Observation
        "salvaged_hitl_242b8dd1",       # Thrawn Intent Clarification
    ]

    # Re-rank kept tasks based on our priority order, default ranking any others.
    print("Re-ranking kept tasks...")
    
    # Create a mapping of task IDs to their sorted ranks
    rank_map = {tid: idx for idx, tid in enumerate(priority_order)}
    
    for task in to_keep:
        tid = task["id"]
        rank = rank_map.get(tid, 999) # fallback rank for unexpected tasks
        archived_at = task["archived_at"]
        
        cursor.execute("SELECT data FROM tasks WHERE id = ?", (tid,))
        data_row = cursor.fetchone()
        if data_row:
            import json
            try:
                task_data = json.loads(data_row[0])
            except Exception:
                task_data = {}
            task_data["rank"] = rank
            task_data["archived_at"] = archived_at
            
            cursor.execute(
                "UPDATE tasks SET rank = ?, archived_at = ?, data = ? WHERE id = ?",
                (rank, archived_at, json.dumps(task_data), tid)
            )

    conn.commit()
    conn.close()
    print("Database updates committed.")

    # Sync back to json files
    bm = BacklogManager(".")
    bm._sync_to_json()
    print("Grooming completed and synchronized successfully.")

if __name__ == "__main__":
    execute_changes = "--execute" in sys.argv
    groom_backlog(execute=execute_changes)