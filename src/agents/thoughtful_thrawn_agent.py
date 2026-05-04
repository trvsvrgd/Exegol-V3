import os
import json
from tools.thrawn_intel_manager import ThrawnIntelManager
from tools.web_search import web_search
from tools.user_prompting import prompt_user_for_clarification
from tools.clarification_engine import refine_strategic_questions, analyze_answer_for_roadmap_impact
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
        """Execute with a clean HandoffContext — no prior session memory required.

        All state is read fresh from the filesystem at invocation time.
        """
        repo_path = handoff.repo_path
        print(f"[{self.name}] Session {handoff.session_id} — waking up for repo: {repo_path}")

        exegol_dir = os.path.join(repo_path, ".exegol")
        os.makedirs(exegol_dir, exist_ok=True)
        intent_file = os.path.join(exegol_dir, "intent.md")

        # 1. Load Intent & Clarifications via Manager (Stateless Refactor)
        mgr = ThrawnIntelManager(repo_path)
        intel = mgr.read_intent()
        
        # Phase 2: Web Search for Intent Enrichment
        if intel.get("objective") and intel.get("objective") != "[Describe the main goal of this repository]":
            print(f"[{self.name}] Researching context for objective: {intel['objective']}")
            search_query = f"industry standards and technical requirements for: {intel['objective']}"
            context_research = web_search(search_query, num_results=3)
            # This research can be used by the LLM in the next steps

        # 2. Identify Open Questions from parsed intel
        open_questions = [q["question"] for q in intel["questions"] if not q["answer"]]
        
        # 3. Synchronize Answered Questions with Roadmap
        answered_questions = [q for q in intel["questions"] if q["answer"]]
        
        if answered_questions:
            roadmap_content = mgr.read_roadmap()
            for aq in answered_questions:
                actions = analyze_answer_for_roadmap_impact(
                    aq["question"], aq["answer"], roadmap_content, 
                    self.llm_client, self.system_prompt
                )
                for action in actions:
                    if action["action"] == "redact":
                        mgr.redact_roadmap_item(action["pattern"])
                    elif action["action"] == "add":
                        mgr.add_roadmap_item(action["section"], action["item"])


        # 4. Enforce Minimum 3 Open Questions
        num_open = len(open_questions)
        if num_open < 3:
            num_needed = 3 - num_open
            print(f"[{self.name}] Only {num_open} open questions found. Generating {num_needed} more to meet the minimum of 3.")
            
            intel_context = json.dumps(intel, indent=2)
            new_qs = refine_strategic_questions(intel_context, self.llm_client, self.system_prompt, count=num_needed)
            
            if new_qs:
                for nq in new_qs:
                    prompt_user_for_clarification(repo_path, nq)
                
                # Refresh open questions list for the summary
                intel = mgr.read_intent()
                open_questions = [q["question"] for q in intel["questions"] if not q["answer"]]
                num_open = len(open_questions)

        summary = f"[{self.name}] Strategic review complete. Currently maintaining {num_open} open clarifying questions."
        if num_open < 3:
            summary += " WARNING: Failed to reach minimum threshold of 3 questions."

        metrics = self._calculate_success_metrics(repo_path)
        log_interaction(
            agent_id=self.name, outcome="success", task_summary=summary,
            repo_path=repo_path, steps_used=1, duration_seconds=5.0,
            session_id=handoff.session_id, metrics=metrics
        )
        self.next_agent_id = "vibe_vader"
        return summary

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
            answered_qs = len([q for q in intel["questions"] if q["answer"]])
            
            if total_qs > 0:
                metrics["questions_answered_rate"] = round(answered_qs / total_qs, 2)
            
            # Heuristic: 24h turnaround if we have active engagement
            metrics["clarification_turnaround_hrs"] = 12.0 if answered_qs > 0 else 0.0

                
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

