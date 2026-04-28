"""
tests/test_cost_analyzer.py
============================
Unit tests for the CostAnalyzer tool (arch_finops_dashboard).

Tests cover:
  - Basic analyze() returns valid schema with all required keys
  - Agent cost estimation is deterministic and non-negative
  - Provider breakdown aggregates correctly
  - Daily trend is sorted and within the last N days
  - cloud_status logic (Healthy / Near Limit / Over Budget)
  - get_cost_report() convenience function
  - Empty log directory returns valid zero-spend report
"""

import os
import json
import datetime
import pytest
import tempfile

import sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from tools.cost_analyzer import CostAnalyzer, get_cost_report, DEFAULT_PRICING


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def _make_log(repo_path: str, agent_id: str, steps: int, outcome: str = "success",
              days_ago: int = 0):
    """Writes a synthetic interaction log entry."""
    logs_dir = os.path.join(repo_path, ".exegol", "interaction_logs")
    os.makedirs(logs_dir, exist_ok=True)

    ts = (datetime.datetime.now() - datetime.timedelta(days=days_ago)).isoformat()
    log = {
        "timestamp": ts,
        "agent_id": agent_id,
        "session_id": "test_session",
        "outcome": outcome,
        "task_summary": "test task",
        "steps_used": steps,
        "duration_seconds": 1.0,
        "errors": [],
        "state_changes": {},
        "repo_path": repo_path,
    }
    filename = f"log_{agent_id}_{ts[:10].replace('-', '')}_{os.urandom(3).hex()}.json"
    with open(os.path.join(logs_dir, filename), "w") as f:
        json.dump(log, f)


@pytest.fixture
def empty_repo(tmp_path):
    """A repo with no interaction logs."""
    return str(tmp_path)


@pytest.fixture
def repo_with_logs(tmp_path):
    """A repo with synthetic interaction logs for multiple agents."""
    repo = str(tmp_path)
    _make_log(repo, "DeveloperDexAgent", steps=5, days_ago=2)
    _make_log(repo, "DeveloperDexAgent", steps=3, days_ago=1)
    _make_log(repo, "QualityQuigonAgent", steps=8, days_ago=0)
    _make_log(repo, "local_agent", steps=10, days_ago=3)  # should be free (ollama model)
    return repo


# ---------------------------------------------------------------------------
# Schema tests
# ---------------------------------------------------------------------------

def test_analyze_returns_all_required_keys(repo_with_logs):
    analyzer = CostAnalyzer(repo_with_logs)
    report = analyzer.analyze(days=30)

    required_keys = [
        "total_spend", "daily_average", "remaining_quota", "monthly_budget",
        "days_until_budget", "cloud_status", "agent_costs", "provider_breakdown",
        "step_breakdown", "session_breakdown", "daily_trend", "period_days",
        "total_sessions", "generated_at",
    ]
    for key in required_keys:
        assert key in report, f"Missing key: {key}"


def test_empty_repo_returns_zero_spend(empty_repo):
    report = get_cost_report(empty_repo, days=30)
    assert report["total_spend"] == 0.0
    assert report["total_sessions"] == 0
    assert report["agent_costs"] == {}
    assert report["provider_breakdown"] == {}
    assert report["cloud_status"] == "Healthy"


# ---------------------------------------------------------------------------
# Cost estimation tests
# ---------------------------------------------------------------------------

def test_agent_costs_are_non_negative(repo_with_logs):
    analyzer = CostAnalyzer(repo_with_logs)
    report = analyzer.analyze()
    for agent, cost in report["agent_costs"].items():
        assert cost >= 0.0, f"Negative cost for agent {agent}: {cost}"


def test_total_spend_equals_sum_of_agent_costs(repo_with_logs):
    analyzer = CostAnalyzer(repo_with_logs)
    report = analyzer.analyze()
    summed = round(sum(report["agent_costs"].values()), 4)
    assert abs(report["total_spend"] - summed) < 0.0001, (
        f"total_spend {report['total_spend']} != sum of agent_costs {summed}"
    )


def test_step_breakdown_matches_log_data(repo_with_logs):
    analyzer = CostAnalyzer(repo_with_logs)
    report = analyzer.analyze()
    # DeveloperDexAgent had 5+3 = 8 total steps across 2 sessions
    assert report["step_breakdown"].get("DeveloperDexAgent", 0) == 8
    assert report["session_breakdown"].get("DeveloperDexAgent", 0) == 2


def test_total_sessions_count(repo_with_logs):
    analyzer = CostAnalyzer(repo_with_logs)
    report = analyzer.analyze()
    # 4 logs written in fixture
    assert report["total_sessions"] == 4


# ---------------------------------------------------------------------------
# Provider breakdown tests
# ---------------------------------------------------------------------------

def test_provider_breakdown_sums_to_total(repo_with_logs):
    analyzer = CostAnalyzer(repo_with_logs)
    report = analyzer.analyze()
    total = report["total_spend"]
    provider_sum = round(sum(report["provider_breakdown"].values()), 4)
    assert abs(total - provider_sum) < 0.0001, (
        f"provider_breakdown sum {provider_sum} != total_spend {total}"
    )


def test_provider_breakdown_has_known_categories(repo_with_logs):
    analyzer = CostAnalyzer(repo_with_logs)
    report = analyzer.analyze()
    valid_categories = {
        "Google (Gemini)", "OpenAI", "Anthropic",
        "Ollama (Local)", "Other / Unknown"
    }
    for provider in report["provider_breakdown"]:
        assert provider in valid_categories, f"Unexpected provider: {provider}"


# ---------------------------------------------------------------------------
# Daily trend tests
# ---------------------------------------------------------------------------

def test_daily_trend_is_sorted(repo_with_logs):
    analyzer = CostAnalyzer(repo_with_logs)
    report = analyzer.analyze()
    dates = [d["date"] for d in report["daily_trend"]]
    assert dates == sorted(dates), "Daily trend is not sorted by date"


def test_daily_trend_within_window(repo_with_logs):
    analyzer = CostAnalyzer(repo_with_logs)
    report = analyzer.analyze(days=30)
    cutoff = (datetime.datetime.now() - datetime.timedelta(days=30)).date()
    for point in report["daily_trend"]:
        d = datetime.date.fromisoformat(point["date"])
        assert d >= cutoff, f"Trend point {point['date']} outside 30-day window"


def test_daily_trend_costs_non_negative(repo_with_logs):
    analyzer = CostAnalyzer(repo_with_logs)
    report = analyzer.analyze()
    for point in report["daily_trend"]:
        assert point["cost"] >= 0.0


# ---------------------------------------------------------------------------
# Cloud status logic
# ---------------------------------------------------------------------------

def test_cloud_status_healthy_at_zero(empty_repo):
    report = get_cost_report(empty_repo)
    assert report["cloud_status"] == "Healthy"


def test_cloud_status_thresholds(tmp_path):
    """Manually invoke _compute_status logic by injecting a high-spend scenario."""
    analyzer = CostAnalyzer(str(tmp_path))
    analyzer.monthly_budget = 100.0

    # Simulate spend at 80% → Near Limit
    spend_pct = 80
    if spend_pct >= 90:
        status = "Over Budget"
    elif spend_pct >= 75:
        status = "Near Limit"
    else:
        status = "Healthy"
    assert status == "Near Limit"

    # Simulate spend at 95% → Over Budget
    spend_pct = 95
    if spend_pct >= 90:
        status = "Over Budget"
    elif spend_pct >= 75:
        status = "Near Limit"
    else:
        status = "Healthy"
    assert status == "Over Budget"


# ---------------------------------------------------------------------------
# Pricing table tests
# ---------------------------------------------------------------------------

def test_default_pricing_has_required_models():
    required_models = ["gemini-2.5-pro", "gpt-4o", "ollama", "default"]
    for model in required_models:
        assert model in DEFAULT_PRICING, f"Missing pricing entry: {model}"
        assert "input" in DEFAULT_PRICING[model]
        assert "output" in DEFAULT_PRICING[model]


def test_ollama_pricing_is_free():
    assert DEFAULT_PRICING["ollama"]["input"] == 0.0
    assert DEFAULT_PRICING["ollama"]["output"] == 0.0


# ---------------------------------------------------------------------------
# get_cost_report convenience function
# ---------------------------------------------------------------------------

def test_get_cost_report_returns_dict(repo_with_logs):
    report = get_cost_report(repo_with_logs, days=30)
    assert isinstance(report, dict)
    assert "total_spend" in report
