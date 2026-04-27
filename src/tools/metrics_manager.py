import os
import json
import datetime
from typing import List, Dict, Any
from tools.fleet_logger import read_interaction_logs

class SuccessMetricsManager:
    """Calculates and persists agent success metrics across the fleet.
    
    Implements Phase 3 Roadmap: Precision/Recall/Drift measurement.
    """
    
    def __init__(self, repo_path: str):
        self.repo_path = repo_path
        self.metrics_dir = os.path.join(repo_path, ".exegol", "fleet_reports")
        os.makedirs(self.metrics_dir, exist_ok=True)
        self.metrics_file = os.path.join(self.metrics_dir, "metrics.json")

    def calculate_metrics(self, days: int = 30) -> Dict[str, Any]:
        """Analyzes interaction logs to calculate per-agent success rates."""
        logs = read_interaction_logs([self.repo_path], days=days)
        
        agent_stats = {}
        
        for log in logs:
            agent_id = log.get("agent_id", "unknown")
            if agent_id not in agent_stats:
                agent_stats[agent_id] = {
                    "total_sessions": 0,
                    "successes": 0,
                    "failures": 0,
                    "avg_steps": 0,
                    "total_duration": 0,
                    "bugs_introduced": 0  # To be enriched by Quigon logs
                }
            
            stats = agent_stats[agent_id]
            stats["total_sessions"] += 1
            if log.get("outcome") == "success":
                stats["successes"] += 1
            elif log.get("outcome") == "failure":
                stats["failures"] += 1
                
            stats["avg_steps"] = (stats["avg_steps"] * (stats["total_sessions"] - 1) + log.get("steps_used", 0)) / stats["total_sessions"]
            stats["total_duration"] += log.get("duration_seconds", 0)

        # Calculate Success Rate
        for agent_id, stats in agent_stats.items():
            stats["success_rate"] = (stats["successes"] / stats["total_sessions"]) if stats["total_sessions"] > 0 else 0
            stats["avg_duration"] = stats["total_duration"] / stats["total_sessions"] if stats["total_sessions"] > 0 else 0

        report = {
            "timestamp": datetime.datetime.now().isoformat(),
            "period_days": days,
            "fleet_aggregate": {
                "total_sessions": len(logs),
                "success_rate": sum(s["successes"] for s in agent_stats.values()) / len(logs) if logs else 0
            },
            "agent_breakdown": agent_stats
        }
        
        self._save_report(report)
        return report

    def _save_report(self, report: Dict[str, Any]):
        try:
            with open(self.metrics_file, "w", encoding="utf-8") as f:
                json.dump(report, f, indent=4)
        except Exception as e:
            print(f"[SuccessMetricsManager] Failed to save metrics: {e}")

    def get_agent_scorecard(self, agent_id: str) -> Dict[str, Any]:
        """Returns a concise scorecard for a specific agent."""
        if not os.path.exists(self.metrics_file):
            self.calculate_metrics()
            
        try:
            with open(self.metrics_file, "r", encoding="utf-8") as f:
                data = json.load(f)
            return data.get("agent_breakdown", {}).get(agent_id, {"error": "No data found"})
        except Exception:
            return {"error": "Failed to read scorecard"}

if __name__ == "__main__":
    # Local test
    manager = SuccessMetricsManager(".")
    print(json.dumps(manager.calculate_metrics(), indent=2))
