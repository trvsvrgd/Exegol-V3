import os
import json
from typing import Optional
from tools.thrawn_intel_manager import ThrawnIntelManager
from tools.slack_tool import post_to_slack

def prompt_user_for_clarification(repo_path: str, question: str, priority: str = "medium") -> bool:
    """
    Injects a clarification question into Thrawn's intent.md and notifies the user via Slack.
    """
    try:
        mgr = ThrawnIntelManager(repo_path)
        intel = mgr.read_intent()
        
        # Check if question already exists
        if any(q["question"] == question for q in intel["questions"]):
            return False
            
        intel["questions"].append({"question": question, "answer": None})
        mgr.save_intent(intel)
        
        # Notify Slack
        msg = f"🤔 *Thrawn Clarification Required* (Priority: {priority})\nRepo: `{repo_path}`\n\n*Question*: {question}\n\n_Please provide answers in the Workbench UI or edit .exegol/intent.md directly._"
        post_to_slack(msg)
        
        return True
    except Exception as e:
        print(f"[user_prompting] Error: {e}")
        return False
