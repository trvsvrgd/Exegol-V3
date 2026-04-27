import os
import json
import datetime
import time
from tools.web_search import web_search
from tools.fleet_logger import log_interaction


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

            backlog_file = os.path.join(exegol_dir, "backlog.json")
            exception_log = os.path.join(exegol_dir, "compliance_exceptions.log")
            
            backlog = []
            if os.path.exists(backlog_file):
                with open(backlog_file, 'r', encoding='utf-8') as f:
                    try:
                        backlog = json.load(f)
                    except:
                        backlog = []

            new_tasks_added = 0
            exceptions_logged = 0

            with open(exception_log, 'a', encoding='utf-8') as elog:
                timestamp = datetime.datetime.now().isoformat()
                elog.write(f"\n--- Compliance Sweep: {timestamp} ---\n")

                for req in found_requirements:
                    # Check if system supports this
                    if req.get("required_capability_id") in system_feature_ids:
                        # Support exists, add as a tracking task if not already there
                        task_exists = any(t.get("source_requirement_id") == req["id"] for t in backlog)
                        if not task_exists:
                            task = {
                                "id": f"comp_{len(backlog)+1:03d}",
                                "summary": f"Compliance Audit: {req['summary']}",
                                "description": req["description"],
                                "priority": req["priority"],
                                "type": "compliance_certification",
                                "status": "pending_prioritization",
                                "source_requirement_id": req["id"]
                            }
                            backlog.append(task)
                            new_tasks_added += 1
                    else:
                        # System does NOT support this requirement — LOG EXCEPTION
                        elog.write(f"[EXCEPTION] System lacks capability '{req.get('required_capability_id')}' for requirement {req['id']}: {req['summary']}\n")
                        exceptions_logged += 1

            # Save backlog
            with open(backlog_file, 'w', encoding='utf-8') as f:
                json.dump(backlog, f, indent=4)

            duration = time.time() - start_time
            summary = f"Compliance sweep complete. Added {new_tasks_added} new tasks to backlog. Logged {exceptions_logged} exceptions."
            
            log_interaction(
                agent_id=self.name,
                outcome="success",
                task_summary=summary,
                repo_path=repo_path,
                steps_used=self._steps_used,
                duration_seconds=duration,
                session_id=handoff.session_id
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
