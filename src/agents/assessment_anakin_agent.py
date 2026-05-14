import os
import json
import datetime
import time
from tools.risk_scorer import calculate_risk_score
from tools.web_search import web_search
from tools.fleet_logger import log_interaction

class AssessmentAnakinAgent:
    """Performs deep-dive risk and impact assessments for proposed changes and infrastructure.
    
    Triggered when high-risk tasks are identified or when architectural changes require 
    an independent safety and performance evaluation.
    """

    def __init__(self, llm_client):
        self.llm_client = llm_client
        self.name = "AssessmentAnakinAgent"
        self.max_steps = 15
        self.tools = ["repo_analyzer", "risk_scorer", "backlog_writer", "web_search"]
        self.success_metrics = {
            "risk_mitigation_rate": {
                "description": "Percentage of high-risk tasks with associated mitigation plans",
                "target": "100%",
                "current": None
            },
            "assessment_accuracy": {
                "description": "Correlation between predicted impact and actual outcome",
                "target": "90%+",
                "current": None
            }
        }
        self.system_prompt = self.llm_client.generate_system_prompt(self)

    def execute(self, handoff):
        """Execute the assessment loop.
        
        1. Analyzes the proposed change or state.
        2. Scores the risk based on complexity, reach, and historical failure data.
        3. Recommends mitigations or flags blocking issues.
        """
        start_time = time.time()
        repo_path = handoff.repo_path
        exegol_dir = os.path.join(repo_path, ".exegol")
        os.makedirs(exegol_dir, exist_ok=True)

        print(f"[{self.name}] Session {handoff.session_id} — Conducting deep-dive risk assessment...")
        
        # Phase 2: Web Search for Risk Research
        print(f"[{self.name}] Researching latest security and performance risks for AI agents...")
        risk_query = "latest AI agent security risks performance bottlenecks and safety failures 2024 2025"
        risk_research = web_search(risk_query, num_results=3)
        
        # REAL risk assessment using git to find recent changes
        from tools.git_tool import run_git_command
        
        # Get staged changes
        staged_diff = run_git_command(repo_path, ["diff", "--cached"])
        if not staged_diff or staged_diff.startswith("Error:"):
            # Fallback to unstaged changes
            staged_diff = run_git_command(repo_path, ["diff"])
        
        if not staged_diff or staged_diff.startswith("Error:"):
            # Fallback to last commit
            staged_diff = run_git_command(repo_path, ["show", "--summary"])
            actual_changes = [{"path": "Last Commit", "content": staged_diff}]
        else:
            # Parse diff for paths (simplified)
            actual_changes = []
            current_path = "unknown"
            for line in staged_diff.splitlines():
                if line.startswith("+++ b/"):
                    current_path = line[6:]
                actual_changes.append({"path": current_path, "content": staged_diff[:1000]}) # Limit content for scoring
        
        risk_data = calculate_risk_score(actual_changes, repo_path)
        
        # Phase 3: LLM Synthesis of findings and recommendations
        analysis_prompt = f"""
        Analyze the following risk research and repo changes to provide a deep-dive assessment.
        
        Risk Research: {json.dumps(risk_research)}
        Recent Changes (Paths): {[c['path'] for c in actual_changes]}
        Risk Scorer Level: {risk_data['level']}
        Risk Scorer Findings: {json.dumps(risk_data['findings'])}
        
        Return a JSON object with:
        - findings: List of strings (specific issues or observations)
        - recommendations: List of strings (actionable mitigations)
        - summary: A one-line summary
        """
        
        try:
            llm_response = self.llm_client.generate(analysis_prompt, system_prompt=self.system_prompt)
            parsed_analysis = self.llm_client.parse_json_response(llm_response)
        except Exception as e:
            print(f"[{self.name}] LLM analysis failed: {e}. Falling back to default.")
            parsed_analysis = {
                "findings": risk_data["findings"],
                "recommendations": ["Review recent changes for security implications."],
                "summary": f"Assessment complete with risk level: {risk_data['level']}"
            }

        assessment_report = {
            "timestamp": datetime.datetime.now().isoformat(),
            "target": "Active Repository State",
            "risk_score": risk_data["score"],
            "risk_level": risk_data["level"],
            "status": "cautionary" if risk_data["level"] in ["high", "critical"] else "optimal",
            "findings": parsed_analysis.get("findings", risk_data["findings"]),
            "recommendations": parsed_analysis.get("recommendations", ["Implement continuous monitoring."]),
            "summary": parsed_analysis.get("summary", ""),
            "research_context": risk_research[:1]
        }

        report_path = os.path.join(exegol_dir, "assessment_report.json")
        with open(report_path, 'w', encoding='utf-8') as f:
            json.dump(assessment_report, f, indent=4)

        summary = assessment_report["summary"] or f"Assessment complete. Risk level: {assessment_report['risk_level']} (Score: {assessment_report['risk_score']}). Findings logged to {report_path}."
        print(f"[{self.name}] {summary}")


        duration = time.time() - start_time
        log_interaction(
            agent_id=self.name,
            outcome="success",
            task_summary=summary,
            repo_path=repo_path,
            duration_seconds=duration,
            session_id=handoff.session_id,
            state_changes={"report_file": report_path}
        )

        return summary
