"""
cost_analyzer.py — Intel Ima FinOps Tool
=========================================
Reads real fleet interaction logs to compute per-agent token consumption
and cost estimates. Powers the Workbench /costs dashboard.

Cost model (estimates based on public pricing, configurable via env):
  - Tokens per step    : ~800  (avg plan + execute tokens per agent step)
  - Input:Output ratio : 70:30
  - Provider costs are resolved from the agent_models.json config
"""

import os
import json
import datetime
from typing import Any, Dict, List

from tools.fleet_logger import read_interaction_logs


# ---------------------------------------------------------------------------
# Default pricing table (USD per 1M tokens).
# These are reference estimates; real deployments should override via env.
# ---------------------------------------------------------------------------

DEFAULT_PRICING: Dict[str, Dict[str, float]] = {
    # model_key: {input_per_1m, output_per_1m}
    "gemini-2.5-pro":    {"input": 1.25,  "output": 10.00},
    "gemini-2.0-flash":  {"input": 0.10,  "output": 0.40},
    "gpt-4o":            {"input": 2.50,  "output": 10.00},
    "gpt-4o-mini":       {"input": 0.15,  "output": 0.60},
    "claude-3-haiku":    {"input": 0.25,  "output": 1.25},
    "claude-3-5-sonnet": {"input": 3.00,  "output": 15.00},
    "ollama":            {"input": 0.00,  "output": 0.00},   # local free
    "local":             {"input": 0.00,  "output": 0.00},
    "default":           {"input": 1.00,  "output": 5.00},   # fallback
}

# Average tokens per agent step (heuristic)
TOKENS_PER_STEP = 800
INPUT_RATIO = 0.70
OUTPUT_RATIO = 0.30


class CostAnalyzer:
    """
    Analyzes fleet interaction logs to produce FinOps cost breakdowns.

    Outputs:
        - total_spend          : float  — estimated USD for the period
        - daily_average        : float
        - remaining_quota      : float  — based on EXEGOL_MONTHLY_BUDGET env
        - days_until_budget    : float  — estimated days until budget exhausted
        - agent_costs          : dict   — {agent_id: usd_cost}
        - provider_breakdown   : dict   — {provider: usd_cost}
        - step_breakdown       : dict   — {agent_id: total_steps}
        - session_breakdown    : dict   — {agent_id: session_count}
        - daily_trend          : list   — [{date, cost}] last 14 days
        - cloud_status         : str    — "Healthy" | "Over Budget" | "Near Limit"
        - period_days          : int
        - generated_at         : str
    """

    def __init__(self, repo_path: str):
        self.repo_path = repo_path
        self.monthly_budget = float(os.getenv("EXEGOL_MONTHLY_BUDGET", "1000.00"))
        self._pricing = self._load_pricing()
        self._agent_models = self._load_agent_models()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def analyze(self, days: int = 30) -> Dict[str, Any]:
        """Main entry point — returns a full FinOps cost report."""
        logs = read_interaction_logs([self.repo_path], days=days)

        agent_costs: Dict[str, float] = {}
        agent_steps: Dict[str, int] = {}
        agent_sessions: Dict[str, int] = {}
        daily_costs: Dict[str, float] = {}

        for log in logs:
            agent_id = log.get("agent_id", "unknown")
            steps = int(log.get("steps_used", 1))
            ts = log.get("timestamp", "")

            # Resolve provider / pricing for this agent
            usd = self._estimate_cost(agent_id, steps)

            agent_costs[agent_id] = round(agent_costs.get(agent_id, 0.0) + usd, 4)
            agent_steps[agent_id] = agent_steps.get(agent_id, 0) + steps
            agent_sessions[agent_id] = agent_sessions.get(agent_id, 0) + 1

            # Daily trend bucket
            day_key = ts[:10] if len(ts) >= 10 else "unknown"
            daily_costs[day_key] = round(daily_costs.get(day_key, 0.0) + usd, 4)

        total_spend = round(sum(agent_costs.values()), 4)

        # Days actually present in data
        days_with_data = len([d for d in daily_costs if d != "unknown"]) or 1
        daily_average = round(total_spend / days_with_data, 4)

        remaining_quota = round(max(0.0, self.monthly_budget - total_spend), 2)

        # Days until budget exhausted (avoid division by zero)
        days_until_budget = (
            round(remaining_quota / daily_average, 1) if daily_average > 0 else None
        )

        # Provider breakdown — aggregate by inferred provider
        provider_breakdown = self._build_provider_breakdown(agent_costs)

        # Daily trend (last 14 days, sorted)
        daily_trend = self._build_daily_trend(daily_costs, days=14)

        # Cloud status
        spend_pct = (total_spend / self.monthly_budget) * 100 if self.monthly_budget > 0 else 0
        if spend_pct >= 90:
            cloud_status = "Over Budget"
        elif spend_pct >= 75:
            cloud_status = "Near Limit"
        else:
            cloud_status = "Healthy"

        return {
            "total_spend": total_spend,
            "daily_average": daily_average,
            "remaining_quota": remaining_quota,
            "monthly_budget": self.monthly_budget,
            "days_until_budget": days_until_budget,
            "cloud_status": cloud_status,
            "agent_costs": agent_costs,
            "provider_breakdown": provider_breakdown,
            "step_breakdown": agent_steps,
            "session_breakdown": agent_sessions,
            "daily_trend": daily_trend,
            "period_days": days,
            "total_sessions": len(logs),
            "generated_at": datetime.datetime.now().isoformat(),
        }

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _estimate_cost(self, agent_id: str, steps: int) -> float:
        """Estimates USD cost for a given agent and step count."""
        model_key = self._resolve_model(agent_id)
        pricing = self._pricing.get(model_key, self._pricing["default"])

        total_tokens = steps * TOKENS_PER_STEP
        input_tokens = total_tokens * INPUT_RATIO
        output_tokens = total_tokens * OUTPUT_RATIO

        input_cost = (input_tokens / 1_000_000) * pricing["input"]
        output_cost = (output_tokens / 1_000_000) * pricing["output"]
        return round(input_cost + output_cost, 6)

    def _resolve_model(self, agent_id: str) -> str:
        """Maps agent_id to a pricing model key."""
        raw_model = self._agent_models.get(agent_id, "default").lower()

        for key in DEFAULT_PRICING:
            if key in raw_model:
                return key

        # Treat anything local/ollama as free
        if "ollama" in raw_model or "local" in raw_model or "llama" in raw_model:
            return "ollama"

        return "default"

    def _build_provider_breakdown(self, agent_costs: Dict[str, float]) -> Dict[str, float]:
        """Aggregates agent costs by cloud provider."""
        providers: Dict[str, float] = {}
        for agent_id, cost in agent_costs.items():
            model_key = self._resolve_model(agent_id)
            if model_key in ("ollama", "local"):
                provider = "Ollama (Local)"
            elif "gemini" in model_key:
                provider = "Google (Gemini)"
            elif "gpt" in model_key:
                provider = "OpenAI"
            elif "claude" in model_key:
                provider = "Anthropic"
            else:
                provider = "Other / Unknown"
            providers[provider] = round(providers.get(provider, 0.0) + cost, 4)
        return providers

    def _build_daily_trend(self, daily_costs: Dict[str, float], days: int = 14) -> List[Dict]:
        """Returns a sorted list of {date, cost} for the last N days."""
        cutoff = (datetime.datetime.now() - datetime.timedelta(days=days)).date()
        trend = []
        for day_str, cost in sorted(daily_costs.items()):
            if day_str == "unknown":
                continue
            try:
                d = datetime.date.fromisoformat(day_str)
                if d >= cutoff:
                    trend.append({"date": day_str, "cost": cost})
            except ValueError:
                continue
        return trend

    def _load_pricing(self) -> Dict[str, Dict[str, float]]:
        """Loads pricing table — uses defaults (override via pricing.json if present)."""
        pricing_path = os.path.join(self.repo_path, "config", "pricing.json")
        if os.path.exists(pricing_path):
            try:
                with open(pricing_path, "r", encoding="utf-8") as f:
                    custom = json.load(f)
                merged = dict(DEFAULT_PRICING)
                merged.update(custom)
                return merged
            except Exception:
                pass
        return dict(DEFAULT_PRICING)

    def _load_agent_models(self) -> Dict[str, str]:
        """Loads agent → model mappings from config/agent_models.json."""
        models_path = os.path.join(self.repo_path, "config", "agent_models.json")
        if os.path.exists(models_path):
            try:
                with open(models_path, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception:
                pass
        return {}


# ---------------------------------------------------------------------------
# Module-level helper (used by IntelImaAgent and the API)
# ---------------------------------------------------------------------------

def get_cost_report(repo_path: str, days: int = 30) -> Dict[str, Any]:
    """Convenience function: analyze and return a full FinOps cost report."""
    analyzer = CostAnalyzer(repo_path)
    return analyzer.analyze(days=days)
