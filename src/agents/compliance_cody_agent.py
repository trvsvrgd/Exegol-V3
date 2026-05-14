import os
import json
import datetime
import time
from tools.web_search import web_search
from tools.fleet_logger import log_interaction
from tools.backlog_manager import BacklogManager
from tools.capability_reviewer import get_compliance_gaps, scan_codebase_for_capabilities
from tools.metrics_manager import SuccessMetricsManager


class ComplianceCodyAgent:
    """Researches global, state, and national ML/LLM requirements and ensures system compatibility.
    
    Triggered monthly to identify new regulatory requirements (e.g. EU AI Act, NIST AI RMF).
    Flags gaps between system capabilities and requirements as exceptions or backlog tasks.
    """

    def __init__(self, llm_client):
        self.llm_client = llm_client
        self.name = "ComplianceCodyAgent"
        self.max_steps = 15
        self._steps_used = 0
        self.tools = ["web_search", "backlog_writer", "capability_reviewer"]
        self.success_metrics = {
            "compliance_gap_coverage": {
                "description": "Percentage of identified regulatory requirements mapped to system capabilities",
                "target": "100%",
                "current": None
            },
            "last_compliance_run": {
                "description": "Timestamp of the last governance and regulatory sweep",
                "target": "Monthly",
                "current": None
            }
        }
        self.system_prompt = self.llm_client.generate_system_prompt(self)
        self.metrics_manager = SuccessMetricsManager(os.getcwd())

    def _calculate_success_metrics(self, repo_path: str) -> dict:
        """Calculates compliance and governance metrics based on recent logs."""
        logs = self.metrics_manager.load_logs(days=30)
        agent_logs = [l for l in logs if l.get("agent_id") == self.name]
        
        if not agent_logs:
            return {
                "compliance_gap_coverage": "0%",
                "last_compliance_run": "Never"
            }

        last_run = agent_logs[-1].get("timestamp")
        
        # Heuristic for coverage: check last successful summary for task counts
        coverage = 0.0
        summary = agent_logs[-1].get("task_summary", "")
        import re
        match = re.search(r"Added (\d+) new tasks", summary)
        if match:
            tasks = int(match.group(1))
            match_exc = re.search(r"Logged (\d+) exceptions", summary)
            exceptions = int(match_exc.group(1)) if match_exc else 0
            total = tasks + exceptions
            coverage = (tasks / total) * 100 if total > 0 else 100.0

        return {
            "compliance_gap_coverage": f"{coverage:.1f}%",
            "last_compliance_run": last_run
        }

    def execute(self, handoff):
        """Execute with a clean HandoffContext — no prior session memory required.
        
        1. Reads system capabilities manifest.
        2. Performs targeted search for latest ML/LLM regulations.
        3. Compares findings with implemented system features.
        4. Updates backlog with compliant tasks and logs exceptions for unsupported requirements.
        """
        start_time = time.time()
        self._steps_used = 0
        repo_path = handoff.repo_path
        exegol_dir = os.path.join(repo_path, ".exegol")
        os.makedirs(exegol_dir, exist_ok=True)

        print(f"[{self.name}] Session {handoff.session_id} — Initiating monthly compliance sweep...")

        try:
            # 1. Load System Capabilities
            capabilities_file = os.path.join(os.path.dirname(os.path.dirname(__file__)), "config", "system_capabilities.json")
            capabilities = {}
            if os.path.exists(capabilities_file):
                with open(capabilities_file, 'r', encoding='utf-8') as f:
                    capabilities = json.load(f)
            
            system_feature_ids = [c["id"] for c in capabilities.get("capabilities", [])]

            # 2. Targeted Research for latest ML/LLM regulations
            print(f"[{self.name}] Searching for latest AI regulations (EU AI Act, NIST, etc.)...")
            search_query = "latest ML LLM AI regulations 2024 2025 EU AI Act NIST RMF requirements"
            search_results = web_search(search_query, num_results=5)
            self._steps_used += 1

            # 3. Analyze search results with LLM to identify specific requirements
            analysis_prompt = f"""
            Regulatory Task: Identify specific requirements from these search results that an autonomous agent fleet must comply with.
            Search Results: {json.dumps(search_results)}
            
            Return a JSON list of requirement objects. Each object should have:
            - 'id': A unique ID (e.g., REG_00X)
            - 'summary': Short name
            - 'description': What is required
            - 'required_capability_id': A string id of the capability needed (e.g. 'isolated_sandboxing', 'user_awareness_disclosure')
            - 'priority': 'high', 'critical', 'medium'
            - 'category': 'Regulatory'
            """
            
            response = self.llm_client.generate(analysis_prompt, system_instruction=self.system_prompt, json_format=True)
            found_requirements = self.llm_client.parse_json_response(response)
            self._steps_used += 1

            if not found_requirements:
                found_requirements = []

            bm = BacklogManager(repo_path)
            new_tasks_added = 0
            exceptions_logged = 0
            
            exception_log_path = os.path.join(exegol_dir, "compliance_exceptions.log")

            # Run full gap analysis using capability_reviewer
            cap_list = capabilities.get("capabilities", [])
            gap_report = get_compliance_gaps(found_requirements, cap_list, llm_client=self.llm_client)
            self._steps_used += 1

            with open(exception_log_path, 'a', encoding='utf-8') as elog:
                timestamp = datetime.datetime.now().isoformat()
                elog.write(f"\n--- Compliance Sweep: {timestamp} (Coverage: {gap_report['coverage_pct']}%) ---\n")

                # Covered requirements → add compliance_certification tasks
                for item in gap_report["covered"]:
                    req = item["requirement"]
                    task = {
                        "id": f"comp_{req['id'].lower()}",
                        "summary": f"Compliance Audit: {req['summary']}",
                        "description": req["description"],
                        "priority": req.get("priority", "medium"),
                        "type": "compliance_certification",
                        "status": "pending_prioritization",
                        "source_requirement_id": req["id"],
                        "mapped_capability_id": item["capability"].get("id"),
                        "match_confidence": item["confidence"],
                        "created_at": datetime.datetime.now().isoformat()
                    }
                    if bm.add_task(task):
                        new_tasks_added += 1

                # Gap items → log exceptions
                for item in gap_report["gaps"]:
                    req = item["requirement"]
                    reason = item.get("reasoning", "No matching capability found")
                    elog.write(f"[EXCEPTION] System lacks capability for {req['id']}: {req['summary']} — {reason}\n")
                    exceptions_logged += 1

            duration = time.time() - start_time
            summary = f"Compliance sweep complete. Added {new_tasks_added} new tasks to backlog. Logged {exceptions_logged} exceptions."
            
            metrics = self._calculate_success_metrics(repo_path)
            log_interaction(
                agent_id=self.name,
                outcome="success",
                task_summary=summary,
                repo_path=repo_path,
                steps_used=self._steps_used,
                duration_seconds=duration,
                session_id=handoff.session_id,
                metrics=metrics
            )
            
            return summary

        except Exception as e:
            duration = time.time() - start_time
            log_interaction(
                agent_id=self.name,
                outcome="failure",
                task_summary=f"Compliance sweep failed: {str(e)}",
                repo_path=repo_path,
                steps_used=self._steps_used,
                duration_seconds=duration,
                errors=[str(e)],
                session_id=handoff.session_id
            )
            return f"[{self.name}] Error during sweep: {e}"
