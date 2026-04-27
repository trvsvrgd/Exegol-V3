import os
import json
import datetime
from typing import List, Dict, Any, Tuple
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
        """Analyzes interaction logs to calculate advanced per-agent metrics."""
        # Baseline (Full period)
        baseline_logs = read_interaction_logs([self.repo_path], days=days)
        # Recent (Last 7 days)
        recent_logs = [log for log in baseline_logs if self._is_within_days(log.get("timestamp"), 7)]
        
        baseline_stats = self._process_logs(baseline_logs)
        recent_stats = self._process_logs(recent_logs)
        
        agent_breakdown = {}
        all_agent_ids = set(baseline_stats.keys()) | set(recent_stats.keys())
        
        for agent_id in all_agent_ids:
            b_stats = baseline_stats.get(agent_id, {})
            r_stats = recent_stats.get(agent_id, {})
            
            # Calculate metrics
            total_sessions = b_stats.get("total_sessions", 0)
            successes = b_stats.get("successes", 0)
            
            # Recall = Success Rate
            recall = successes / total_sessions if total_sessions > 0 else 0
            
            # Precision = Successes that are qualitatively high quality
            # (In this version, we mock precision based on successful outcomes without errors)
            # In a full impl, this would join with LLMJudge scores.
            precision = max(0.0, (successes - b_stats.get("errors_count", 0)) / successes) if successes > 0 else 0
            
            # Drift = Recent Success Rate - Baseline Success Rate
            recent_success_rate = r_stats.get("success_rate", 0)
            baseline_success_rate = b_stats.get("success_rate", 0)
            drift = recent_success_rate - baseline_success_rate
            
            agent_breakdown[agent_id] = {
                "recall": round(recall, 2),
                "precision": round(precision, 2),
                "drift": round(drift, 2),
                "avg_steps": round(b_stats.get("avg_steps", 0), 1),
                "avg_duration": round(b_stats.get("avg_duration", 0), 1),
                "total_sessions": total_sessions,
                "status": "improving" if drift > 0.05 else "declining" if drift < -0.05 else "stable"
            }

        report = {
            "timestamp": datetime.datetime.now().isoformat(),
            "period_days": days,
            "fleet_aggregate": {
                "total_sessions": len(baseline_logs),
                "avg_recall": round(sum(a["recall"] for a in agent_breakdown.values()) / len(agent_breakdown), 2) if agent_breakdown else 0,
                "avg_precision": round(sum(a["precision"] for a in agent_breakdown.values()) / len(agent_breakdown), 2) if agent_breakdown else 0,
                "overall_drift": round(sum(a["drift"] for a in agent_breakdown.values()) / len(agent_breakdown), 2) if agent_breakdown else 0
            },
            "agent_breakdown": agent_breakdown
        }
        
        self._save_report(report)
        return report

    def _is_within_days(self, ts_str: str, days: int) -> bool:
        if not ts_str: return False
        try:
            ts = datetime.datetime.fromisoformat(ts_str)
            cutoff = datetime.datetime.now() - datetime.timedelta(days=days)
            return ts >= cutoff
        except ValueError:
            return False

    def _process_logs(self, logs: List[dict]) -> Dict[str, Any]:
        stats = {}
        for log in logs:
            agent_id = log.get("agent_id", "unknown")
            if agent_id not in stats:
                stats[agent_id] = {
                    "total_sessions": 0,
                    "successes": 0,
                    "failures": 0,
                    "avg_steps": 0,
                    "total_duration": 0,
                    "errors_count": 0
                }
            
            s = stats[agent_id]
            s["total_sessions"] += 1
            if log.get("outcome") == "success":
                s["successes"] += 1
            elif log.get("outcome") == "failure":
                s["failures"] += 1
            
            s["errors_count"] += len(log.get("errors", []))
            s["avg_steps"] = (s["avg_steps"] * (s["total_sessions"] - 1) + log.get("steps_used", 0)) / s["total_sessions"]
            s["total_duration"] += log.get("duration_seconds", 0)

        for agent_id, s in stats.items():
            s["success_rate"] = s["successes"] / s["total_sessions"] if s["total_sessions"] > 0 else 0
            s["avg_duration"] = s["total_duration"] / s["total_sessions"] if s["total_sessions"] > 0 else 0
            
        return stats

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
