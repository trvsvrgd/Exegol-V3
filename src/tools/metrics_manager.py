import os
import json
import datetime
from typing import List, Dict, Any, Optional
from tools.fleet_logger import read_interaction_logs
from agents.registry import AGENT_REGISTRY


DEFAULT_METRICS_START_DATE = "2026-05-31"


def _to_local_naive(value: datetime.datetime) -> datetime.datetime:
    if value.tzinfo is None:
        return value
    return value.astimezone().replace(tzinfo=None)


def parse_metrics_start_date(start_date: Optional[str]) -> Optional[datetime.datetime]:
    if not start_date:
        return None

    value = start_date.strip()
    if not value:
        return None

    try:
        if len(value) == 10:
            return datetime.datetime.combine(
                datetime.date.fromisoformat(value),
                datetime.time.min,
            )
        return _to_local_naive(datetime.datetime.fromisoformat(value.replace("Z", "+00:00")))
    except ValueError as exc:
        raise ValueError(f"Invalid metrics start_date '{start_date}'. Use YYYY-MM-DD or ISO datetime.") from exc


def parse_log_timestamp(timestamp: Optional[str]) -> Optional[datetime.datetime]:
    if not timestamp:
        return None
    try:
        return _to_local_naive(datetime.datetime.fromisoformat(timestamp.replace("Z", "+00:00")))
    except ValueError:
        return None


def filter_logs_since(logs: List[dict], period_start: Optional[datetime.datetime]) -> List[dict]:
    if period_start is None:
        return logs
    filtered = []
    for log in logs:
        timestamp = parse_log_timestamp(log.get("timestamp"))
        if timestamp and timestamp >= period_start:
            filtered.append(log)
    return filtered


def calculate_read_days_for_start(period_start: Optional[datetime.datetime], default_days: int) -> int:
    if period_start is None:
        return default_days
    elapsed_days = (datetime.datetime.now().date() - period_start.date()).days + 1
    return max(default_days, elapsed_days, 1)


class SuccessMetricsManager:
    """Calculates and persists agent success metrics across the fleet.
    
    Implements Phase 3 Roadmap: Precision/Recall/Drift measurement.
    """
    
    def __init__(self, repo_path: str):
        self.repo_path = repo_path
        self.metrics_dir = os.path.join(repo_path, ".exegol", "fleet_reports")
        os.makedirs(self.metrics_dir, exist_ok=True)
        self.metrics_file = os.path.join(self.metrics_dir, "metrics.json")
        self.judge_dir = os.path.join(repo_path, ".exegol", "optimizer_reports", "judge_evals")
        self.observations_file = os.path.join(repo_path, ".exegol", "human_observations.json")
        os.makedirs(self.judge_dir, exist_ok=True)

    def _load_human_observations(self) -> Dict[str, str]:
        """Loads human observations from the .exegol directory."""
        if os.path.exists(self.observations_file):
            try:
                with open(self.observations_file, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception as e:
                print(f"[SuccessMetricsManager] Failed to load human observations: {e}")
        return {}

    def calculate_metrics(
        self,
        days: int = 30,
        enable_live_judge: bool = False,
        start_date: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Analyzes interaction logs to calculate advanced per-agent metrics."""
        period_start = parse_metrics_start_date(start_date)
        read_days = calculate_read_days_for_start(period_start, days)
        period_end = datetime.datetime.now()

        # Baseline (filtered reporting period)
        baseline_logs = filter_logs_since(
            read_interaction_logs([self.repo_path], days=read_days),
            period_start,
        )
        # Recent (Last 7 days)
        recent_logs = [log for log in baseline_logs if self._is_within_days(log.get("timestamp"), 7)]
        
        baseline_stats = self._process_logs(baseline_logs)
        recent_stats = self._process_logs(recent_logs)
        observations = self._load_human_observations()
        
        agent_breakdown = {}
        # Ensure only registered Star Wars agents are included
        all_agent_ids = set(AGENT_REGISTRY.keys())
        
        for agent_id in all_agent_ids:
            b_stats = baseline_stats.get(agent_id, {})
            r_stats = recent_stats.get(agent_id, {})
            
            # Calculate metrics
            total_sessions = b_stats.get("total_sessions", 0)
            successes = b_stats.get("successes", 0)
            
            # Recall = Success Rate
            recall = successes / total_sessions if total_sessions > 0 else 0
            
            # Precision = Qualitative quality score from LLM Judge
            # We fetch cached judge scores or sample recent sessions for auditing.
            agent_obs = {k: v for k, v in observations.items() if agent_id.startswith(k) or k in agent_id}
            precision = self._calculate_real_precision(
                agent_id,
                b_stats.get("logs", []),
                agent_obs,
                enable_live_judge=enable_live_judge,
            )
            
            # Drift = Recent Success Rate - Baseline Success Rate
            recent_success_rate = r_stats.get("success_rate", 0)
            baseline_success_rate = b_stats.get("success_rate", 0)
            drift = recent_success_rate - baseline_success_rate
            
            agent_breakdown[agent_id] = {
                "recall": round(recall, 2),
                "precision": round(precision, 2),
                "drift": round(drift, 2),
                "success_rate": round(recall, 2),
                "avg_steps": round(b_stats.get("avg_steps", 0), 1),
                "avg_duration": round(b_stats.get("avg_duration", 0), 1),
                "avg_prompts": round(b_stats.get("avg_prompts", 0), 1),
                "avg_tokens": round(b_stats.get("avg_tokens", 0), 0),
                "bugs_introduced": b_stats.get("errors_count", 0),
                "total_sessions": total_sessions,
                "status": "improving" if drift > 0.05 else "declining" if drift < -0.05 else "stable",
                "tools_accessible": AGENT_REGISTRY.get(agent_id, {}).get("tools", []),
                "custom_metrics": b_stats.get("latest_metrics", {}),
                "human_observations": list(agent_obs.values())
            }

        if period_start is None:
            period_start = period_end - datetime.timedelta(days=days)
            period_label = f"Last {days} days"
            period_days = days
        else:
            period_days = max(1, (period_end.date() - period_start.date()).days + 1)
            period_label = f"Since {period_start.date().isoformat()}"

        report = {
            "timestamp": period_end.isoformat(),
            "period_days": period_days,
            "period_start": period_start.isoformat(),
            "period_end": period_end.isoformat(),
            "period_label": period_label,
            "fleet_aggregate": {
                "total_sessions": len(baseline_logs),
                "success_rate": round(
                    sum(a["total_sessions"] * a["success_rate"] for a in agent_breakdown.values())
                    / sum(a["total_sessions"] for a in agent_breakdown.values()),
                    2,
                ) if any(a["total_sessions"] for a in agent_breakdown.values()) else 0,
                "avg_recall": round(sum(a["recall"] for a in agent_breakdown.values()) / len(agent_breakdown), 2) if agent_breakdown else 0,
                "avg_precision": round(sum(a["precision"] for a in agent_breakdown.values()) / len(agent_breakdown), 2) if agent_breakdown else 0,
                "overall_drift": round(sum(a["drift"] for a in agent_breakdown.values()) / len(agent_breakdown), 2) if agent_breakdown else 0
            },
            "agent_breakdown": agent_breakdown,
            "human_observations": observations
        }
        
        self._save_report(report)
        return report

    def _is_within_days(self, ts_str: str, days: int) -> bool:
        ts = parse_log_timestamp(ts_str)
        if not ts:
            return False
        cutoff = datetime.datetime.now() - datetime.timedelta(days=days)
        return ts >= cutoff

    def _process_logs(self, logs: List[dict]) -> Dict[str, Any]:
        stats = {}
        # Map class names to IDs to handle mixed logging
        class_to_id = {v["class"]: k for k, v in AGENT_REGISTRY.items()}
        
        for log in logs:
            raw_id = log.get("agent_id", "unknown")
            # Normalize to snake_case ID from registry
            agent_id = raw_id if raw_id in AGENT_REGISTRY else class_to_id.get(raw_id, raw_id)
            
            if agent_id not in stats:
                stats[agent_id] = {
                    "total_sessions": 0,
                    "successes": 0,
                    "failures": 0,
                    "avg_steps": 0,
                    "total_duration": 0,
                    "total_prompts": 0,
                    "total_tokens": 0,
                    "errors_count": 0,
                    "logs": []
                }
            
            s = stats[agent_id]
            s["total_sessions"] += 1
            s["logs"].append(log)
            if log.get("outcome") == "success":
                s["successes"] += 1
            elif log.get("outcome") == "failure":
                s["failures"] += 1
            
            s["errors_count"] += len(log.get("errors", []))
            s["avg_steps"] = (s["avg_steps"] * (s["total_sessions"] - 1) + log.get("steps_used", 0)) / s["total_sessions"]
            s["total_duration"] += log.get("duration_seconds", 0)
            s["total_prompts"] += log.get("prompt_count", 0)
            s["total_tokens"] += log.get("token_usage", 0)
            
            # Capture latest custom metrics
            if log.get("metrics"):
                s["latest_metrics"] = log.get("metrics")

        for agent_id, s in stats.items():
            s["success_rate"] = s["successes"] / s["total_sessions"] if s["total_sessions"] > 0 else 0
            s["avg_duration"] = s["total_duration"] / s["total_sessions"] if s["total_sessions"] > 0 else 0
            s["avg_prompts"] = s["total_prompts"] / s["total_sessions"] if s["total_sessions"] > 0 else 0
            s["avg_tokens"] = s["total_tokens"] / s["total_sessions"] if s["total_sessions"] > 0 else 0
            
        return stats

    def _calculate_real_precision(
        self,
        agent_id: str,
        logs: List[dict],
        observations: Dict[str, str] = None,
        enable_live_judge: bool = False,
    ) -> float:
        """Calculates a qualitative precision score by sampling sessions with LLMJudge."""
        if not logs:
            return 0.0
            
        # 1. Look for existing judge evaluations in the judge_dir
        scored_sessions = 0
        total_score = 0.0
        
        # Sample up to 5 successful sessions for auditing if not already judged
        successful_logs = [l for l in logs if l.get("outcome") == "success"]
        if not successful_logs:
            return 0.0
            
        sample_size = min(len(successful_logs), 3)
        import random
        # Use a stable seed for consistent reporting within a day
        random.seed(datetime.date.today().toordinal())
        sample = random.sample(successful_logs, sample_size)
        
        for log in sample:
            session_id = log.get("session_id", "unknown")
            judge_file = os.path.join(self.judge_dir, f"judge_{session_id}.json")
            
            evaluation = None
            if os.path.exists(judge_file):
                try:
                    with open(judge_file, "r") as f:
                        evaluation = json.load(f)
                except:
                    pass
            
            # 2. Try to get precision from QualityQuigon metrics in related logs
            if not evaluation:
                # Look for a QualityQuigon log in the same session
                quigon_logs = [l for l in logs if l.get("agent_id") == "QualityQuigonAgent" and l.get("session_id") == session_id]
                if quigon_logs:
                    q_log = quigon_logs[0]
                    der_str = q_log.get("metrics", {}).get("defect_escape_rate", "100%").replace("%", "")
                    try:
                        der = float(der_str) / 100.0
                        total_score += (1.0 - der)
                        scored_sessions += 1
                        continue # Found a good metric, skip LLM Judge
                    except:
                        pass

            # 3. Optional live audit. Disabled for API/dashboard calls so metrics
            # stay bounded and do not block on local or remote model providers.
            if enable_live_judge and (not evaluation or evaluation.get("error")):
                from tools.llm_judge import LLMJudge

                print(f"[SuccessMetricsManager] Auditing session {session_id} for {agent_id}...")
                evaluation = LLMJudge.evaluate_session(log)
                if evaluation and not evaluation.get("error"):
                    try:
                        with open(judge_file, "w") as f:
                            json.dump(evaluation, f, indent=2)
                    except:
                        pass

            if evaluation and "score" in evaluation:
                # Score is 0-10, normalize to 0.0-1.0
                total_score += (evaluation["score"] / 10.0)
                scored_sessions += 1
                
        if scored_sessions > 0:
            return round(total_score / scored_sessions, 2)
            
        # 4. Fallback: Use heuristic based on errors and boost/penalize based on human observations
        successes = len(successful_logs)
        errors = sum(len(l.get("errors", [])) for l in successful_logs)
        base_precision = max(0.0, (successes - errors) / successes) if successes > 0 else 0.0
        
        if observations:
            # Analyze observations for sentiment/keywords to adjust precision
            obs_text = " ".join(observations.values()).lower()
            if any(kw in obs_text for kw in ["excellent", "perfect", "solid", "reliable", "validated"]):
                base_precision = min(1.0, base_precision + 0.15)
            elif any(kw in obs_text for kw in ["buggy", "unreliable", "failing", "poor", "error-prone"]):
                base_precision = max(0.0, base_precision - 0.2)
            else:
                # Neutral boost for having oversight
                base_precision = min(1.0, base_precision + 0.05)
            
        return round(base_precision, 2)

    def _save_report(self, report: Dict[str, Any]):
        try:
            with open(self.metrics_file, "w", encoding="utf-8") as f:
                json.dump(report, f, indent=4)
        except Exception as e:
            print(f"[SuccessMetricsManager] Failed to save metrics: {e}")

    def load_logs(self, days: int = 7) -> List[Dict[str, Any]]:
        """Wraps fleet_logger.read_interaction_logs for convenience."""
        return read_interaction_logs([self.repo_path], days=days)


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
