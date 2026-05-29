import json
import time

import pytest

from agents.registry import AGENT_REGISTRY
from tools.fleet_logger import log_interaction
from tools.metrics_manager import SuccessMetricsManager


def test_metrics_calculation_is_fast_without_live_judge(tmp_path, monkeypatch):
    agent_id = next(iter(AGENT_REGISTRY))
    repo_path = str(tmp_path)
    log_interaction(
        agent_id=agent_id,
        outcome="success",
        task_summary="metrics smoke",
        repo_path=repo_path,
        steps_used=3,
        duration_seconds=1.5,
        session_id="metrics-smoke-session",
    )

    def fail_live_judge(_log):
        raise AssertionError("live LLM judge should not run during default metrics calculation")

    from tools import llm_judge

    monkeypatch.setattr(llm_judge.LLMJudge, "evaluate_session", fail_live_judge)

    started = time.monotonic()
    report = SuccessMetricsManager(repo_path).calculate_metrics()
    elapsed = time.monotonic() - started

    assert elapsed < 2
    assert report["fleet_aggregate"]["total_sessions"] == 1
    assert report["fleet_aggregate"]["success_rate"] == 1.0
    assert report["agent_breakdown"][agent_id]["total_sessions"] == 1
    assert report["agent_breakdown"][agent_id]["bugs_introduced"] == 0

    metrics_file = tmp_path / ".exegol" / "fleet_reports" / "metrics.json"
    saved = json.loads(metrics_file.read_text(encoding="utf-8"))
    assert saved["fleet_aggregate"]["success_rate"] == 1.0
