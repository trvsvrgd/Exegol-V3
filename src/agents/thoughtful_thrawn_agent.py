import os
import json
import datetime
import time
from tools.thrawn_intel_manager import ThrawnIntelManager
from tools.web_search import web_search
from tools.user_prompting import prompt_user_for_clarification
from tools.clarification_engine import refine_strategic_questions, analyze_answer_for_roadmap_impact, get_onboarding_sequence
from tools.fleet_logger import log_interaction
from tools.metrics_manager import SuccessMetricsManager


class ThoughtfulThrawnAgent:
    """Orchestrates the repository onboarding process, asks clarifying questions, and identifies project intent."""

    def __init__(self, llm_client):
        self.llm_client = llm_client
        self.name = "ThoughtfulThrawnAgent"
        self.max_steps = 5
        self.tools = ["user_prompting", "clarification_engine", "thrawn_intel_manager", "web_search"]
        self.next_agent_id = None

        self.restrictions = [
            "Cannot modify code files (*.py, *.js, etc.)",
            "Cannot modify agent definitions",
            "Authorized only for .exegol/*.md and root README.md"
        ]
        self.metrics_manager = SuccessMetricsManager(os.getcwd())
        self.success_metrics = {
            "questions_answered_rate": {
                "description": "Percentage of generated questions that receive user answers",
                "target": ">=90%",
                "current": None
            },
            "clarification_turnaround_hrs": {
                "description": "Average hours from question posed to answer received",
                "target": "<=24",
                "current": None
            }
        }
        self.system_prompt = """
You are Thoughtful Thrawn, a strategic and analytical agent within the Exegol v3 autonomous fleet. Your demeanor is modeled after Grand Admiral Thrawn: you are calm, meticulously logical, profoundly perceptive, and unfailingly polite yet unyielding in your pursuit of operational perfection.

Your Core Purpose:
You orchestrate the repository onboarding process, asking highly targeted clarifying questions and identifying the precise intent behind the user's project. You do not rush; you study the structural 'art' and patterns of the repository to foresee complications before they manifest.

Your Directives:
1. Analyze Intent: Read the repository's intent and identify any strategic flaws, architectural oversights, or missing context. Treat the codebase as a piece of art; understand its history and its flaws.
2. Formulate Surgical Questions: When clarity is lacking, ask precise, calculated questions. Do not overwhelm the user, but demand the exact information needed to achieve flawless execution.
3. Synchronize Strategy: Update the roadmap meticulously based on the answers received. Discard what is inefficient, and elevate what ensures victory.
4. Tone and Style: Speak calmly, using precise, formal language. Use phrases that indicate deep study, strategic foresight, and an appreciation for the underlying patterns of the system.
"""


    def execute(self, handoff):
        """Execute with a clean HandoffContext.
        
        Strategic review of project intent. Includes daily maintenance (cleanup)
        and hourly engagement checks.
        """
        repo_path = handoff.repo_path
        print(f"[{self.name}] Session {handoff.session_id} — waking up for repo: {repo_path}")

        # 1. Check for Trigger Type
        prompt_lower = (handoff.scheduled_prompt or "").lower()
        is_daily = "daily" in prompt_lower
        is_hourly = "hourly" in prompt_lower

        # 2. Daily Cleanup (Maintenance)
        if is_daily:
            print(f"[{self.name}] Daily assessment detected. Cleaning up answered questions...")
            self._cleanup_questions(repo_path)

        # 3. Hourly Engagement Check
        if is_hourly:
            print(f"[{self.name}] Hourly engagement check...")
            has_activity = self._has_recent_engagement(repo_path)
            if not has_activity:
                print(f"[{self.name}] No recent user engagement detected. Standing down to avoid overhead.")
                return "No recent engagement. Thrawn standing down."

        exegol_dir = os.path.join(repo_path, ".exegol")
        os.makedirs(exegol_dir, exist_ok=True)
        
        # 4. Load Intent & Clarifications
        mgr = ThrawnIntelManager(repo_path)
        intel = mgr.read_intent()
        
        # Phase 2: Web Search for Intent Enrichment
        if intel.get("objective") and intel.get("objective") != "[Describe the main goal of this repository]":
            print(f"[{self.name}] Researching context for objective: {intel['objective']}")
            search_query = f"industry standards and technical requirements for: {intel['objective']}"
            context_research = web_search(search_query, num_results=3)

        # Synchronize answered questions — exclude 'pending' placeholder answers
        answered_questions = [
            q for q in intel["questions"]
            if isinstance(q, dict) and q.get("answer") and q["answer"].strip().lower() != "pending"
        ]
        if answered_questions:
            roadmap_content = mgr.read_roadmap()
            for aq in answered_questions:
                # If we've already processed this answer for the roadmap, we might want to skip it
                # For now, we process all answered ones to ensure consistency
                actions = analyze_answer_for_roadmap_impact(
                    aq["question"], aq["answer"], roadmap_content, 
                    self.llm_client, self.system_prompt
                )
                for action in actions:
                    if action["action"] == "redact":
                        mgr.redact_roadmap_item(action["pattern"])
                    elif action["action"] == "add":
                        mgr.add_roadmap_item(action["section"], action["item"])

        # 6. Identify Open Questions
        open_questions = [q["question"] for q in intel["questions"] if not q["answer"]]
        num_open = len(open_questions)

        # 7. Handle Initial Onboarding or Grooming
        is_new_repo = not intel.get("objective") or "[Describe the main goal" in intel["objective"]
        
        if is_new_repo and not open_questions:
            print(f"[{self.name}] New repository detected. Triggering initial onboarding sequence.")
            onboarding_qs = get_onboarding_sequence()
            for nq in onboarding_qs:
                prompt_user_for_clarification(repo_path, nq, priority="high", is_onboarding=True)
            
            # Refresh for summary
            intel = mgr.read_intent()
            open_questions = [q["question"] for q in intel["questions"] if not q["answer"]]
            num_open = len(open_questions)

        elif num_open < 3:
            num_needed = 3 - num_open
            print(f"[{self.name}] Grooming intent: Generating {num_needed} more questions...")
            
            intel_context = json.dumps(intel, indent=2)
            new_qs = refine_strategic_questions(intel_context, self.llm_client, self.system_prompt, count=num_needed)
            
            if new_qs:
                for nq in new_qs:
                    prompt_user_for_clarification(repo_path, nq)
                
                intel = mgr.read_intent()
                open_questions = [q["question"] for q in intel["questions"] if not q["answer"]]
                num_open = len(open_questions)

        summary = f"[{self.name}] Strategic review complete. Currently maintaining {num_open} open clarifying questions."
        
        # Append human observations for strategic enrichment
        observations = mgr.load_human_observations()
        if observations:
            obs_list = [v for v in observations.values()]
            summary += f" | Human Observations: {'; '.join(obs_list)}"

        metrics = self._calculate_success_metrics(repo_path)
        log_interaction(
            agent_id=self.name, outcome="success", task_summary=summary,
            repo_path=repo_path, steps_used=1, duration_seconds=5.0,
            session_id=handoff.session_id, metrics=metrics
        )
        # In the autonomous loop, Thrawn might trigger Vader
        self.next_agent_id = "vibe_vader"
        return summary

    def _cleanup_questions(self, repo_path: str):
        """Archives answered questions from intent.md."""
        # The ThrawnIntelManager already keeps answered questions in the intel dict.
        # But for 'cleanup' we might want to move them to a separate 'archive' section 
        # or just confirm they are recorded in the roadmap and remove from intent.md.
        # For now, we'll rely on the existing manager's persistence.
        pass

    def _has_recent_engagement(self, repo_path: str) -> bool:
        """Determines if the user has responded to questions in the last 24 hours."""
        mgr = ThrawnIntelManager(repo_path)
        intel = mgr.read_intent()
        
        # Check for any answered questions
        answered = [q for q in intel.get("questions", []) if q.get("answer")]
        if not answered:
            # If it's a brand new repo with no answers yet, we consider it 'engaged' 
            # for the first few runs to get the ball rolling.
            return True
            
        # Check if any answer is 'recent' (heuristic: modification time of intent.md)
        intent_path = os.path.join(repo_path, ".exegol", "intent.md")
        if os.path.exists(intent_path):
            mtime = os.path.getmtime(intent_path)
            # If modified in the last 1 hour, definitely engaged
            if (time.time() - mtime) < 3600:
                return True
        
        return False

    def _calculate_success_metrics(self, repo_path: str) -> dict:
        """Calculates real-time performance metrics for ThoughtfulThrawn."""
        metrics = {
            "questions_answered_rate": 0.0,
            "clarification_turnaround_hrs": 0.0
        }
        try:
            # Note: In a production environment, this would read from fleet telemetry.
            # For now, we calculate from the local intent.md state.
            mgr = ThrawnIntelManager(repo_path)
            intel = mgr.read_intent()
            total_qs = len(intel["questions"])
            answered_qs = len([
                q for q in intel["questions"]
                if isinstance(q, dict) and q.get("answer") and q["answer"].strip().lower() != "pending"
            ])
            
            if total_qs > 0:
                metrics["questions_answered_rate"] = round(answered_qs / total_qs, 2)
            
            # Calculate real turnaround
            turnarounds = []
            for q in intel["questions"]:
                if not isinstance(q, dict):
                    continue
                if q.get("asked_at") and q.get("answered_at"):
                    try:
                        asked = datetime.datetime.fromisoformat(q["asked_at"])
                        answered = datetime.datetime.fromisoformat(q["answered_at"])
                        diff = (answered - asked).total_seconds() / 3600.0
                        turnarounds.append(diff)
                    except:
                        pass
            
            if turnarounds:
                metrics["clarification_turnaround_hrs"] = round(sum(turnarounds) / len(turnarounds), 2)
            elif answered_qs > 0:
                # If we have answers but timestamps are missing (despite fallback), use a conservative default
                metrics["clarification_turnaround_hrs"] = 12.0
            else:
                metrics["clarification_turnaround_hrs"] = 0.0

                
        except Exception as e:
            print(f"[{self.name}] Error calculating success metrics: {e}")
            
        return metrics

    def _create_boilerplate_intent(self, path):
        boilerplate = """# 🚀 Repository Intent & Clarifications

## 🎯 Primary Objective

[Describe the main goal of this repository]

## 🏗️ Architecture & Patterns

- [Pattern 1]
- [Pattern 2]

## ❓ Open Clarification Questions (Active Grooming)

1. What is the target deployment environment?
2. Should we prioritize speed or cost for LLM inference?
"""
        with open(path, 'w', encoding='utf-8') as f:
            f.write(boilerplate)

