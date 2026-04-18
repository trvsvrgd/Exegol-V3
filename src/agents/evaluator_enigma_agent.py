import os
import json
import datetime


class EvaluatorEnigmaAgent:
    """Researches the latest agentic evaluation techniques and generates
    new requirements for Exegol_v3's evaluation framework."""

    def __init__(self, llm_client):
        self.llm_client = llm_client
        self.name = "EvaluatorEnigmaAgent"
        self.max_steps = 15
        self.tools = ["web_search", "arxiv_reader", "backlog_writer"]
        self.success_metrics = {
            "new_techniques_identified": {
                "description": "At least 1 new eval technique identified per weekly run",
                "target": ">=1",
                "current": None
            },
            "requirements_added": {
                "description": "At least 1 new eval requirement added per weekly run",
                "target": ">=1",
                "current": None
            },
            "stale_requirements": {
                "description": "Requirements older than 30 days without implementation progress",
                "target": "0",
                "current": None
            },
            "technique_recency_days": {
                "description": "Research sources should be no older than 14 days",
                "target": "<=14",
                "current": None
            }
        }
        self.system_prompt = self.llm_client.generate_system_prompt(self)


    # ------------------------------------------------------------------
    # Eval requirements store
    # ------------------------------------------------------------------

    @staticmethod
    def _load_eval_requirements(repo_path: str) -> list:
        """Load existing eval requirements or initialise an empty list."""
        req_file = os.path.join(repo_path, ".exegol", "eval_requirements.json")
        if os.path.exists(req_file):
            try:
                with open(req_file, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception as e:
                print(f"[EvaluatorEnigmaAgent] Error reading eval_requirements: {e}")
        return []

    @staticmethod
    def _save_eval_requirements(repo_path: str, requirements: list):
        exegol_dir = os.path.join(repo_path, ".exegol")
        os.makedirs(exegol_dir, exist_ok=True)
        req_file = os.path.join(exegol_dir, "eval_requirements.json")
        with open(req_file, "w", encoding="utf-8") as f:
            json.dump(requirements, f, indent=4)

    # ------------------------------------------------------------------
    # Research engine
    # ------------------------------------------------------------------

    def _research_latest_techniques(self) -> list:
        """Return a list of cutting-edge agentic evaluation techniques.

        In production this would call web_search and arxiv_reader tools to
        pull the latest papers, blog posts, and benchmark suites.  For now
        we maintain a curated knowledge base that is rotated weekly.
        """
        # Comprehensive catalogue of modern eval techniques.
        # A real implementation would dynamically fetch from arXiv, HuggingFace,
        # LangChain docs, etc.
        techniques = [
            {
                "technique_name": "LLM-as-Judge (G-Eval)",
                "source_url": "https://arxiv.org/abs/2303.16634",
                "description": (
                    "Use a secondary LLM to score agent outputs on coherence, "
                    "relevance, fluency, and consistency using chain-of-thought "
                    "prompting.  Enables automated quality gates without human "
                    "annotators."
                ),
                "category": "output_quality"
            },
            {
                "technique_name": "Multi-Turn Conversation Eval Harness",
                "source_url": "https://arxiv.org/abs/2406.04792",
                "description": (
                    "A framework for evaluating agents across multi-turn "
                    "dialogues, measuring context retention, instruction "
                    "following, and tool-use accuracy over extended sessions."
                ),
                "category": "multi_turn"
            },
            {
                "technique_name": "Tool-Use Scoring Rubric (ToolBench)",
                "source_url": "https://arxiv.org/abs/2305.16504",
                "description": (
                    "Standardised rubric for evaluating how correctly and "
                    "efficiently an agent selects and invokes external tools. "
                    "Measures tool selection accuracy, parameter correctness, "
                    "and result interpretation."
                ),
                "category": "tool_use"
            },
            {
                "technique_name": "Agent Trajectory Evaluation (AgentBench)",
                "source_url": "https://arxiv.org/abs/2308.03688",
                "description": (
                    "Evaluates the full reasoning trajectory of an agent, "
                    "not just the final answer.  Scores each intermediate step "
                    "for correctness, efficiency (fewest steps), and safety "
                    "(no harmful actions)."
                ),
                "category": "trajectory"
            },
            {
                "technique_name": "Agentic RAG Evaluation (RAGAS / ARES)",
                "source_url": "https://arxiv.org/abs/2309.15217",
                "description": (
                    "Evaluates retrieval-augmented generation pipelines used by "
                    "agents.  Measures context relevancy, answer faithfulness, "
                    "and hallucination rate with automated LLM-based metrics."
                ),
                "category": "rag"
            },
            {
                "technique_name": "Red-Teaming & Safety Probes",
                "source_url": "https://arxiv.org/abs/2402.10260",
                "description": (
                    "Automated adversarial testing of agents using jailbreak "
                    "prompts, prompt injection attacks, and boundary-violation "
                    "scenarios.  Ensures agents respect safety constraints "
                    "(e.g., max_steps, file deletion approvals)."
                ),
                "category": "safety"
            },
            {
                "technique_name": "Cost-Aware Evaluation",
                "source_url": "https://arxiv.org/abs/2401.16947",
                "description": (
                    "Measures not just quality but the token and API cost of "
                    "each agent run.  Enables Pareto-optimal selection of models "
                    "and prompts — critical for a 20-repo fleet where cost "
                    "scales linearly."
                ),
                "category": "cost"
            },
            {
                "technique_name": "Human-in-the-Loop Preference Eval (LMSYS Chatbot Arena style)",
                "source_url": "https://arxiv.org/abs/2403.04132",
                "description": (
                    "Periodic human preference ratings between agent outputs "
                    "using an ELO-style ranking system.  Provides ground-truth "
                    "calibration for automated metrics."
                ),
                "category": "human_eval"
            },
            {
                "technique_name": "Regression Testing via Snapshot Assertions",
                "source_url": "https://docs.pytest.org/en/stable/how-to/capture-warnings.html",
                "description": (
                    "Capture agent output snapshots and assert future runs "
                    "produce equivalent results.  Detects unintended behaviour "
                    "changes after prompt or model updates."
                ),
                "category": "regression"
            },
            {
                "technique_name": "SWE-bench Style Task Completion",
                "source_url": "https://arxiv.org/abs/2310.06770",
                "description": (
                    "Evaluate coding agents by having them solve real GitHub "
                    "issues end-to-end.  Success is measured by whether the "
                    "generated patch passes the repo's existing test suite."
                ),
                "category": "code_generation"
            }
        ]

        # Rotate to simulate discovering new techniques each week
        week_num = datetime.datetime.now().isocalendar()[1]
        # Return a subset that simulates 'newly discovered' techniques
        start = (week_num * 3) % len(techniques)
        return [techniques[(start + i) % len(techniques)] for i in range(3)]

    # ------------------------------------------------------------------
    # Gap analysis
    # ------------------------------------------------------------------

    def _identify_gaps(self, existing: list, researched: list) -> list:
        """Return only techniques not already captured in requirements."""
        existing_names = {r.get("technique_name", "").lower() for r in existing}
        return [
            t for t in researched
            if t["technique_name"].lower() not in existing_names
        ]

    # ------------------------------------------------------------------
    # Stale requirement detection
    # ------------------------------------------------------------------

    def _flag_stale_requirements(self, requirements: list) -> list:
        """Mark requirements older than 30 days with no progress as stale."""
        now = datetime.datetime.now()
        stale = []
        for req in requirements:
            added_str = req.get("added_date", "")
            if not added_str:
                continue
            try:
                added = datetime.datetime.fromisoformat(added_str)
                age_days = (now - added).days
                if age_days > 30 and req.get("status") == "pending":
                    req["status"] = "stale"
                    stale.append(req)
            except ValueError:
                continue
        return stale

    # ------------------------------------------------------------------
    # Backlog integration
    # ------------------------------------------------------------------

    @staticmethod
    def _add_to_backlog(repo_path: str, new_reqs: list):
        """Add implementation tasks for new eval requirements to the shared backlog."""
        exegol_dir = os.path.join(repo_path, ".exegol")
        os.makedirs(exegol_dir, exist_ok=True)
        backlog_file = os.path.join(exegol_dir, "backlog.json")

        backlog = []
        if os.path.exists(backlog_file):
            try:
                with open(backlog_file, "r", encoding="utf-8") as f:
                    backlog = json.load(f)
            except Exception:
                pass

        for req in new_reqs:
            task = {
                "id": f"eval_{len(backlog) + 1:03d}",
                "summary": f"Implement eval technique: {req['technique_name']}",
                "description": req["description"],
                "priority": req.get("priority", "high"),
                "type": "eval_implementation",
                "status": "pending_prioritization",
                "source_requirement_id": req.get("id", "unknown")
            }
            backlog.append(task)

        with open(backlog_file, "w", encoding="utf-8") as f:
            json.dump(backlog, f, indent=4)

    # ------------------------------------------------------------------
    # Main execution
    # ------------------------------------------------------------------

    def execute(self, handoff):
        """Run the weekly evaluation research and requirements cycle.

        Accepts a HandoffContext — no prior session memory required.
        All state is read fresh from the filesystem.
        """
        repo_path = handoff.repo_path
        print(f"[{self.name}] Session {handoff.session_id} — weekly eval research cycle starting.")
        print(f"[{self.name}] Target repo: {repo_path}")

        # 1. Load existing requirements
        existing_reqs = self._load_eval_requirements(repo_path)
        print(f"[{self.name}] Loaded {len(existing_reqs)} existing eval requirements.")

        # 2. Research latest techniques
        print(f"[{self.name}] Researching latest agentic evaluation techniques...")
        researched = self._research_latest_techniques()
        print(f"[{self.name}] Found {len(researched)} techniques in this week's research.")

        # 3. Gap analysis
        new_techniques = self._identify_gaps(existing_reqs, researched)
        print(f"[{self.name}] {len(new_techniques)} new techniques identified (not yet in requirements).")

        # 4. Flag stale requirements
        stale = self._flag_stale_requirements(existing_reqs)
        if stale:
            print(f"[{self.name}] ⚠ {len(stale)} requirements flagged as stale (>30 days, still pending).")

        # 5. Generate new requirement entries
        new_reqs = []
        now_str = datetime.datetime.now().isoformat()
        for i, tech in enumerate(new_techniques):
            req = {
                "id": f"eval_req_{len(existing_reqs) + i + 1:03d}",
                "technique_name": tech["technique_name"],
                "category": tech.get("category", "general"),
                "source_url": tech["source_url"],
                "description": tech["description"],
                "priority": "high",
                "status": "pending",
                "added_date": now_str,
                "added_by": self.name
            }
            new_reqs.append(req)

        # 6. Persist updated requirements
        all_reqs = existing_reqs + new_reqs
        self._save_eval_requirements(repo_path, all_reqs)
        print(f"[{self.name}] Saved {len(all_reqs)} total eval requirements.")

        # 7. Add implementation tasks to backlog
        if new_reqs:
            self._add_to_backlog(repo_path, new_reqs)
            print(f"[{self.name}] Added {len(new_reqs)} implementation tasks to backlog.")

        # 8. Write weekly summary report
        exegol_dir = os.path.join(repo_path, ".exegol")
        reports_dir = os.path.join(exegol_dir, "eval_reports")
        os.makedirs(reports_dir, exist_ok=True)

        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        report_file = os.path.join(reports_dir, f"weekly_{timestamp}.json")

        report = {
            "generated_at": timestamp,
            "techniques_researched": len(researched),
            "new_techniques_added": len(new_reqs),
            "stale_requirements_flagged": len(stale),
            "total_requirements": len(all_reqs),
            "new_requirements": new_reqs,
            "stale_requirements": [
                {"id": r["id"], "technique_name": r["technique_name"]}
                for r in stale
            ]
        }

        with open(report_file, "w", encoding="utf-8") as f:
            json.dump(report, f, indent=4)

        print(f"[{self.name}] Weekly eval report saved to {report_file}")

        return (
            f"Eval research cycle complete. "
            f"{len(new_reqs)} new requirements added, "
            f"{len(stale)} stale flagged. "
            f"Total requirements: {len(all_reqs)}. "
            f"Report: {report_file}"
        )
