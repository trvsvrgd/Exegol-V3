"""
Test script for the SecretManager key rotation system.
Validates: audit, health checks, HITL escalation, and rotation.
"""
import os
import sys
import json

project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
sys.path.insert(0, os.path.join(project_root, 'src'))

from dotenv import load_dotenv
load_dotenv(os.path.join(project_root, '.env'))

from tools.secret_manager import SecretManager

def main():
    print("=" * 60)
    print("  SecretManager - End-to-End Test")
    print("=" * 60)

    sm = SecretManager(project_root)

    # --- 1. Full Audit ---
    print("\n[1/4] Running full key audit...")
    summary = sm.get_status_summary()
    print(f"  Total managed keys: {summary['total_managed_keys']}")
    print(f"  Healthy:            {summary['healthy']}")
    print(f"  Unhealthy:          {summary['unhealthy']}")
    print(f"  Overdue:            {summary['overdue_for_rotation']}")
    print()

    for key in summary["keys"]:
        status_icon = {
            "healthy": "[OK]",
            "expired": "[EXPIRED]",
            "placeholder": "[PLACEHOLDER]",
            "unknown": "[?]",
            "missing": "[MISSING]",
        }.get(key["health_status"], "[?]")

        print(f"  {status_icon:14s} {key['display_name']:30s} age={key['age_days']}d  fp={key['fingerprint'][:12]}...")

    # --- 2. Individual Health Check ---
    print("\n[2/4] Individual health checks...")
    for env_var in ["GEMINI_API_KEY", "ANTHROPIC_API_KEY", "SLACK_BOT_TOKEN"]:
        result = sm.check_key_health(env_var)
        print(f"  {env_var}: {result['status']} - {result['detail'][:80]}")

    # --- 3. HITL Escalation ---
    print("\n[3/4] Escalating unhealthy keys to HITL queue...")
    escalated = sm.escalate_unhealthy_keys()
    print(f"  Escalated {len(escalated)} tasks: {escalated}")

    # --- 4. Verify HITL queue ---
    print("\n[4/4] Verifying HITL queue...")
    hitl_path = os.path.join(project_root, ".exegol", "user_action_required.json")
    with open(hitl_path, "r", encoding="utf-8") as f:
        queue = json.load(f)

    rotation_tasks = [t for t in queue if t.get("id", "").startswith("hitl_rotate_")]
    print(f"  Found {len(rotation_tasks)} key rotation tasks in HITL queue:")
    for t in rotation_tasks:
        print(f"    - {t['id']}: {t['task']} [{t['status']}]")

    # --- 5. Verify metadata file ---
    print("\n[5] Metadata file check...")
    meta_path = os.path.join(project_root, "config", "secret_metadata.json")
    if os.path.exists(meta_path):
        with open(meta_path, "r") as f:
            meta = json.load(f)
        print(f"  Tracking {len(meta)} keys in {meta_path}")
    else:
        print(f"  ERROR: Metadata file not found at {meta_path}")

    print("\n" + "=" * 60)
    print("  Test Complete")
    print("=" * 60)

if __name__ == "__main__":
    main()
