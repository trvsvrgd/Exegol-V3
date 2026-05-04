import os
import json
import datetime
import time
from tools.backlog_manager import BacklogManager
from tools.arxiv_reader import search_arxiv
from tools.web_search import web_search
from tools.fleet_logger import log_interaction


class EvaluatorEzraAgent:
    """Evaluates agent performance, reviews logs, and validates outputs against success metrics."""

    def __init__(self, llm_client):
        self.llm_client = llm_client
        self.name = "EvaluatorEzraAgent"
        self.max_steps = 15
        self.tools = ["web_search", "arxiv_reader", "backlog_writer", "llm_judge"]
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
                print(f"[EvaluatorEzraAgent] Error reading eval_requirements: {e}")
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

        Dynamically researches arXiv, blogs, and benchmarks via web_search.
        """
        print(f"[{self.name}] Searching for latest agentic evaluation techniques...")
        search_query = "latest autonomous agent evaluation techniques benchmarks 2024 2025"
        
        # 1. Search Web
        search_results = web_search(search_query, num_results=5)
        
        # 2. Search arXiv
        arxiv_results = search_arxiv("agent evaluation benchmarks", max_results=5)
        
        # Combine results for analysis
        combined_research = {
            "web": search_results,
            "arxiv": [
                {
                    "title": r["title"],
                    "summary": r["summary"],
                    "url": r["link"]
                } for r in arxiv_results
            ]
        }

        # Use LLM to extract specific techniques from search results
        analysis_prompt = f"""
        Research Task: Identify specific, actionable agentic evaluation techniques from these search results.
        Research Results: {json.dumps(combined_research)}
        
        Return a JSON list of technique objects. Each object should have:
        - 'technique_name': Name of the technique
        - 'source_url': URL to the paper or blog
        - 'description': Brief summary of what it measures
        - 'category': One of ['output_quality', 'multi_turn', 'tool_use', 'trajectory', 'rag', 'safety', 'cost', 'human_eval', 'regression', 'code_generation']
        """
        
        response = self.llm_client.generate(analysis_prompt, system_instruction=self.system_prompt, json_format=True)
        techniques = self.llm_client.parse_json_response(response)
        
        if not techniques or not isinstance(techniques, list):
            # Fallback to a minimal list if analysis fails
            return [
                {
                    "technique_name": "LLM-as-Judge (G-Eval)",
                    "source_url": "https://arxiv.org/abs/2303.16634",
                    "description": "Use a secondary LLM to score agent outputs on coherence and relevance.",
                    "category": "output_quality"
                }
            ]
            
        return techniques

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
        bm = BacklogManager(repo_path)

        for req in new_reqs:
            task = {
                "id": f"eval_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}_{req['technique_name'][:10].lower().replace(' ', '_')}",
                "summary": f"Implement eval technique: {req['technique_name']}",
                "description": req["description"],
                "priority": req.get("priority", "high"),
                "type": "eval_implementation",
                "status": "pending_prioritization",
                "source_requirement_id": req.get("id", "unknown"),
                "created_at": datetime.datetime.now().isoformat()
            }
            bm.add_task(task)

    # ------------------------------------------------------------------
    # Main execution
    # ------------------------------------------------------------------

    def execute(self, handoff):
        """Run the weekly evaluation research and requirements cycle.

        Accepts a HandoffContext — no prior session memory required.
        All state is read fresh from the filesystem.
        """
        start_time = time.time()
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

        # 8b. Qualitative Evaluation Engine (LLMJudge Integration)
        try:
            from tools.llm_judge import LLMJudge
            print(f"[{self.name}] Running qualitative evaluations on active fleet...")
            agent_evals = {}
            # Evaluate key agents
            for target_agent in ["developer_dex", "product_poe", "architect_artoo", "quality_quigon"]:
                eval_result = LLMJudge.audit_agent(target_agent, limit=3)
                if "error" not in eval_result:
                    agent_evals[target_agent] = eval_result
            report["agent_evaluations"] = agent_evals
            print(f"[{self.name}] Completed evaluations for {len(agent_evals)} agents.")
        except Exception as e:
            print(f"[{self.name}] Failed to run LLM Judge evaluations: {e}")
            report["agent_evaluations"] = {"error": str(e)}

        with open(report_file, "w", encoding="utf-8") as f:
            json.dump(report, f, indent=4)

        print(f"[{self.name}] Weekly eval report saved to {report_file}")

        duration = time.time() - start_time
        summary_msg = (
            f"Eval research cycle complete. "
            f"{len(new_reqs)} new requirements added, "
            f"{len(stale)} stale flagged. "
            f"Total requirements: {len(all_reqs)}. "
            f"Report: {report_file}"
        )

        log_interaction(
            agent_id=self.name,
            outcome="success",
            task_summary=summary_msg,
            repo_path=repo_path,
            session_id=handoff.session_id,
            state_changes={"report_file": report_file}
        )

        return summary_msg
