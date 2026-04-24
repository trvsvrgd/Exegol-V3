import json
from typing import List, Dict, Any, Optional
from tools.interaction_log_reader import read_logs

class AgentEvaluator:
    """Computes objective success metrics (Precision, Recall, Drift) for the fleet."""

    # Baseline expected steps for common task types
    TASK_BASELINES = {
        "security_fix": 4,
        "feature_implementation": 6,
        "bug_fix": 3,
        "documentation": 2,
        "refactor": 5
    }

    @classmethod
    def calculate_metrics(cls, agent_id: str, limit: int = 100) -> Dict[str, Any]:
        """Calculates PRD metrics for a specific agent based on historical logs."""
        logs = read_logs(limit=limit)
        agent_logs = [l for l in logs if l.get("agent_id") == agent_id]
        
        if not agent_logs:
            return {"error": "No logs found for agent"}

        total_sessions = len(agent_logs)
        successful_sessions = sum(1 for l in agent_logs if l.get("outcome") == "success")
        
        total_steps_taken = sum(l.get("steps_used", 0) for l in agent_logs)
        
        # 1. Precision: Ratio of successful outcome to total effort (sessions)
        # In this context, we treat a session as a 'predicted' success.
        precision = successful_sessions / total_sessions if total_sessions > 0 else 0
        
        # 2. Drift: How far the agent is from the baseline expected steps
        drifts = []
        for log in agent_logs:
            task_type = log.get("task_type", "bug_fix")
            baseline = cls.TASK_BASELINES.get(task_type, 4)
            actual = log.get("steps_used", baseline)
            drift = actual / baseline if baseline > 0 else 1.0
            drifts.append(drift)
        
        avg_drift = sum(drifts) / len(drifts) if drifts else 1.0
        
        # 3. Efficiency (Inverse of Drift)
        efficiency = 1.0 / avg_drift if avg_drift > 0 else 0
        
        return {
            "agent_id": agent_id,
            "sample_size": total_sessions,
            "success_rate": f"{precision * 100:.1f}%",
            "avg_steps_per_session": round(total_steps_taken / total_sessions, 2) if total_sessions > 0 else 0,
            "avg_drift": round(avg_drift, 2),
            "efficiency_score": round(efficiency * 100, 1),
            "status": "HEALTHY" if avg_drift < 1.5 and precision > 0.7 else "DEGRADED"
        }

    @classmethod
    def get_fleet_report(cls) -> Dict[str, Any]:
        """Generates a high-level success report for all active agents."""
        logs = read_logs(limit=200)
        agents = list(set(l.get("agent_id") for l in logs if l.get("agent_id")))
        
        report = {}
        for agent_id in agents:
            report[agent_id] = cls.calculate_metrics(agent_id)
            
        return report

if __name__ == "__main__":
    # Test with Developer Dex
    metrics = AgentEvaluator.calculate_metrics("developer_dex")
    print(json.dumps(metrics, indent=2))
