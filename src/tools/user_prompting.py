import os
import datetime
from tools.thrawn_intel_manager import ThrawnIntelManager
from tools.slack_tool import post_to_slack
from tools.state_manager import StateManager

def prompt_user_for_clarification(repo_path: str, question: str, priority: str = "medium", is_onboarding: bool = False) -> bool:
    """
    Standardized onboarding tool that injects a question into Thrawn's intent logic, 
    notifies Slack, and creates a blocking HITL entry for the Workbench.
    """
    try:
        # 1. Update the local Intent Markdown
        mgr = ThrawnIntelManager(repo_path)
        intel = mgr.read_intent()
        
        # Check if question already exists to avoid spam
        # Guard against malformed (non-dict) entries in the questions list
        valid_questions = [q for q in intel["questions"] if isinstance(q, dict)]
        if any(q.get("question") == question for q in valid_questions):
            print(f"[user_prompting] Question already exists, skipping: {question[:50]}...")
            return False
        intel["questions"] = valid_questions  # Sanitize the list in-place before writing
            
        intel["questions"].append({
            "question": question, 
            "answer": None,
            "asked_at": datetime.datetime.now().isoformat()
        })
        mgr.save_intent(intel)
        
        # 2. Escalate to Human Action Required (HITL)
        sm = StateManager(repo_path)
        category = "onboarding" if is_onboarding else "intent"
        task_summary = f"Thrawn: {question[:60]}..."
        
        sm.add_hitl_task(
            summary=task_summary,
            category=category,
            context=f"Thoughtful Thrawn requires project clarity: '{question}'\n\nPlease answer in .exegol/intent.md or the Workbench."
        )
        
        # 3. Notify Slack with rich formatting
        priority_emoji = "🔴" if priority == "high" else "🟡"
        onboarding_prefix = "🚀 *Onboarding* | " if is_onboarding else ""
        
        msg = (
            f"{onboarding_prefix}{priority_emoji} *Thrawn Clarification Required*\n"
            f"Repo: `{os.path.basename(repo_path)}`\n\n"
            f"*Question*: {question}\n\n"
            f"_Please provide answers in the Workbench UI or edit .exegol/intent.md directly._"
        )
        post_to_slack(msg)
        
        return True
    except Exception as e:
        print(f"[user_prompting] Critical Error: {e}")
        return False
