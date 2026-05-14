"""
dex_real_run.py — Real-LLM execution of DeveloperDexAgent

Bypasses the mock LLM and runs through the full production stack:
  SessionManager -> InferenceManager(gemini) -> DeveloperDexAgent -> QualityQuigon handoff

Task: user_task_8a86a45b — Sync vibe-coding, Exegol UI, and Slack interaction layers.

Usage:
    python scripts/dex_real_run.py
    python scripts/dex_real_run.py --provider anthropic
"""
import os
import sys
import argparse

# --- PATH SETUP ---
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
src_path = os.path.join(project_root, 'src')
for p in [project_root, src_path]:
    if p not in sys.path:
        sys.path.insert(0, p)

# Load .env before any other imports
from dotenv import load_dotenv
load_dotenv(os.path.join(project_root, '.env'))

def main():
    parser = argparse.ArgumentParser(description="Run DeveloperDexAgent with a real LLM")
    parser.add_argument(
        "--provider",
        default="gemini",
        choices=["gemini", "anthropic", "ollama"],
        help="LLM provider to use (default: gemini)"
    )
    parser.add_argument(
        "--task-id",
        default="user_task_8a86a45b",
        help="Backlog task ID to execute (default: user_task_8a86a45b)"
    )
    args = parser.parse_args()

    print(f"\n{'='*60}")
    print(f"  DeveloperDex — Real Run  |  provider={args.provider}")
    print(f"{'='*60}\n")

    from session_manager import SessionManager
    from handoff import HandoffContext
    from inference.inference_manager import InferenceManager
    from inference.llm_client import TrackingLLMClient
    import hmac, hashlib, time

    repo_path = project_root
    agent_id  = "developer_dex"
    provider  = args.provider

    # --- Build a signed HandoffContext (mirrors orchestrator._sign_handoff) ---
    handoff = HandoffContext(
        repo_path=repo_path,
        agent_id=agent_id,
        task_id=args.task_id,
        model_routing=provider,
        max_steps=20,
        session_id=f"real_dex_{int(time.time())}",
        scheduled_prompt="go",          # merged with active_prompt.md by the agent
    )

    # Sign the handoff (required by SessionManager HMAC check)
    secret = os.getenv("EXEGOL_HMAC_SECRET", "dev-secret-keep-it-safe")
    data   = f"{handoff.repo_path}|{handoff.agent_id}|{handoff.session_id}|{handoff.timestamp}"
    sig    = hmac.new(secret.encode(), data.encode(), hashlib.sha256).hexdigest()
    object.__setattr__(handoff, "signature", sig)

    print(f"[RealRun] Session ID : {handoff.session_id}")
    print(f"[RealRun] Provider   : {provider}")
    print(f"[RealRun] Task ID    : {args.task_id}")
    print(f"[RealRun] Repo path  : {repo_path}\n")

    # --- Spawn via SessionManager (production path) ---
    sm = SessionManager(log_every_session=True)
    result = sm.spawn_agent_session(
        agent_id=agent_id,
        module_path="agents.developer_dex_agent",
        class_name="DeveloperDexAgent",
        handoff=handoff,
    )

    # --- Report ---
    print(f"\n{'='*60}")
    print(f"  Execution Complete")
    print(f"{'='*60}")
    print(f"  Outcome        : {result.outcome}")
    print(f"  Duration       : {result.duration_seconds:.1f}s")
    print(f"  Steps used     : {result.steps_used}")
    print(f"  Prompt count   : {result.prompt_count}")
    print(f"  Tokens (est.)  : {result.token_usage}")
    print(f"  Next agent     : {result.next_agent_id or 'none'}")
    print(f"  Snapshot hash  : {result.snapshot_hash or 'none'}")
    if result.errors:
        print(f"  Errors         :")
        for e in result.errors:
            print(f"    - {e}")
    print(f"\n  Summary:\n  {result.output_summary[:500]}")
    print(f"{'='*60}\n")

    return 0 if result.outcome == "success" else 1


if __name__ == "__main__":
    sys.exit(main())
