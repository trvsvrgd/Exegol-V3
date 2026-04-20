import os
import json
import datetime


class ComplianceCodyAgent:
    """Researches global, state, and national ML/LLM requirements and ensures system compatibility.
    
    Triggered monthly to identify new regulatory requirements (e.g. EU AI Act, NIST AI RMF).
    Flags gaps between system capabilities and requirements as exceptions or backlog tasks.
    """

    def __init__(self, llm_client):
        self.llm_client = llm_client
        self.name = "ComplianceCodyAgent"
        self.max_steps = 15
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
        repo_path = handoff.repo_path
        exegol_dir = os.path.join(repo_path, ".exegol")
        os.makedirs(exegol_dir, exist_ok=True)

        print(f"[{self.name}] Session {handoff.session_id} — Initiating monthly compliance sweep...")

        # 1. Load System Capabilities
        capabilities_file = os.path.join(os.path.dirname(os.path.dirname(__file__)), "config", "system_capabilities.json")
        capabilities = {}
        if os.path.exists(capabilities_file):
            with open(capabilities_file, 'r', encoding='utf-8') as f:
                capabilities = json.load(f)
        
        system_feature_ids = [c["id"] for c in capabilities.get("capabilities", [])]

        # 2. Targeted Research (Mock findings including Regulatory & Agentic Evaluation)
        found_requirements = [
            {
                "id": "REG_001_AI_ACT",
                "summary": "EU AI Act Transparency Requirement",
                "description": "Systems must inform users that they are interacting with an AI system.",
                "required_capability_id": "user_awareness_disclosure",
                "priority": "high",
                "category": "Regulatory"
            },
            {
                "id": "REG_002_NIST",
                "summary": "NIST AI RMF - Execution Sandboxing",
                "description": "AI execution environments must be isolated to prevent unauthorized system access.",
                "required_capability_id": "isolated_sandboxing",
                "priority": "critical",
                "category": "Regulatory"
            },
            {
                "id": "EVAL_001_BENCH",
                "summary": "AgentBench v2 - Trajectory Efficiency",
                "description": "Autonomous agents must be evaluated for reasoning trajectory efficiency (minimum steps to solution).",
                "required_capability_id": "trajectory_analysis",
                "priority": "medium",
                "category": "Agentic Evaluation"
            },
            {
                "id": "EVAL_002_SAFETY",
                "summary": "OWASP Agent Security - Jailbreak Probing",
                "description": "Agents must undergo automated red-teaming for prompt injection and jailbreak scenarios.",
                "required_capability_id": "safety_red_teaming",
                "priority": "high",
                "category": "Agentic Evaluation"
            }
        ]

        backlog_file = os.path.join(exegol_dir, "backlog.json")
        exception_log = os.path.join(exegol_dir, "compliance_exceptions.log")
        
        backlog = []
        if os.path.exists(backlog_file):
            with open(backlog_file, 'r', encoding='utf-8') as f:
                backlog = json.load(f)

        new_tasks_added = 0
        exceptions_logged = 0

        with open(exception_log, 'a', encoding='utf-8') as elog:
            timestamp = datetime.datetime.now().isoformat()
            elog.write(f"\n--- Compliance Sweep: {timestamp} ---\n")

            for req in found_requirements:
                # Check if system supports this
                if req["required_capability_id"] in system_feature_ids:
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
                    elog.write(f"[EXCEPTION] System lacks capability '{req['required_capability_id']}' for requirement {req['id']}: {req['summary']}\n")
                    exceptions_logged += 1

        # Save backlog
        with open(backlog_file, 'w', encoding='utf-8') as f:
            json.dump(backlog, f, indent=4)

        summary = f"Compliance sweep complete. Added {new_tasks_added} new tasks to backlog. Logged {exceptions_logged} exceptions to {exception_log}."
        print(f"[{self.name}] {summary}")
        return summary
