import json
import os
from typing import Dict, Any, Optional
from inference.llm_client import GeminiClient, OllamaClient, AnthropicClient

class LLMJudge:
    """Uses a high-reasoning LLM to qualitatively evaluate agent task completion."""

    JUDGE_PROMPT = """
    You are the Exegol Fleet Auditor performing a G-Eval assessment. Your task is to evaluate the work performed by an autonomous agent based on its session log.
    
    You must evaluate the following four G-Eval criteria using Chain-of-Thought reasoning:
    1. **Coherence**: Is the agent's overall plan and execution logical and well-structured?
    2. **Relevance**: Did the agent's actions directly address the assigned task description without unnecessary deviations?
    3. **Fluency**: Are the agent's outputs, logs, and summaries clear, readable, and professionally communicated?
    4. **Consistency**: Do the agent's final outputs align with its stated goals and the initial task requirements without contradictions?
    
    Session Log Summary:
    {log_summary}
    
    First, think step-by-step (Chain-of-Thought) about each of the four criteria. Then, provide your final evaluation.
    
    Provide your evaluation in JSON format with the following keys:
    - chain_of_thought: (Your step-by-step reasoning for coherence, relevance, fluency, and consistency)
    - score: (0-10)
    - rationale: (Brief explanation summarizing the evaluation)
    - category: (EXCELLENT, GOOD, FAIR, POOR, CRITICAL_FAILURE)
    - suggestions: (List of improvements)
    """

    @classmethod
    def evaluate_session(cls, session_log: Dict[str, Any]) -> Dict[str, Any]:
        """Calls an LLM to judge a specific agent session."""
        try:
            # Prepare a concise summary for the judge
            summary = {
                "agent_id": session_log.get("agent_id"),
                "task": session_log.get("task_description"),
                "outcome": session_log.get("outcome"),
                "steps_used": session_log.get("steps_used"),
                "errors": session_log.get("errors", []),
                "output": session_log.get("output_summary")
            }
            
            # Use local provider (Ollama) by default for cost-efficiency and privacy
            provider = os.getenv("LLM_JUDGE_PROVIDER", "ollama")
            if provider == "gemini":
                client = GeminiClient(model=os.getenv("GEMINI_JUDGE_MODEL", "gemini-1.5-pro"))
            elif provider == "anthropic":
                client = AnthropicClient(model=os.getenv("ANTHROPIC_JUDGE_MODEL", "claude-3-5-sonnet-20240620"))
            else:
                # Use default Ollama model if OLLAMA_JUDGE_MODEL is not set
                client = OllamaClient(model=os.getenv("OLLAMA_JUDGE_MODEL")) 
            
            prompt = cls.JUDGE_PROMPT.format(log_summary=json.dumps(summary, indent=2))
            
            response_text = client.generate(prompt, json_format=True)
            return client.parse_json_response(response_text)
        except Exception as e:
            print(f"[LLMJudge] Error evaluating session: {e}")
            return {"score": 0, "category": "ERROR", "rationale": str(e)}

    @classmethod
    def audit_agent(cls, agent_id: str, limit: int = 3) -> Dict[str, Any]:
        """Audits the most recent sessions of an agent and returns an average score."""
        from tools.interaction_log_reader import read_logs
        logs = read_logs(limit=20)
        agent_logs = [l for l in logs if l.get("agent_id") == agent_id][:limit]
        
        if not agent_logs:
            return {"error": "No logs found for agent"}
            
        evals = []
        for log in agent_logs:
            evals.append(cls.evaluate_session(log))
            
        avg_score = sum(e.get("score", 0) for e in evals) / len(evals) if evals else 0
        
        return {
            "agent_id": agent_id,
            "audit_count": len(evals),
            "average_judge_score": round(avg_score, 1),
            "detailed_evals": evals
        }

if __name__ == "__main__":
    # Test audit
    report = LLMJudge.audit_agent("developer_dex", limit=1)
    print(json.dumps(report, indent=2))
