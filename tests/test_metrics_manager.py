import json
import time

import pytest

from agents.registry import AGENT_REGISTRY
from tools.fleet_logger import log_interaction
from tools.metrics_manager import SuccessMetricsManager


def _write_interaction_log(
    repo_path,
    filename,
    timestamp,
    agent_id,
    outcome="success",
    session_id=None,
    errors=None,
):
    logs_dir = repo_path / ".exegol" / "interaction_logs"
    logs_dir.mkdir(parents=True, exist_ok=True)
    payload = {
        "timestamp": timestamp,
        "agent_id": agent_id,
        "session_id": session_id or filename.removesuffix(".json"),
        "outcome": outcome,
        "task_summary": f"{agent_id} {outcome}",
        "steps_used": 1,
        "duration_seconds": 1.0,
        "errors": errors or [],
        "state_changes": {},
        "metrics": {},
        "token_usage": 0,
        "prompt_count": 0,
        "repo_path": str(repo_path),
    }
    (logs_dir / filename).write_text(json.dumps(payload), encoding="utf-8")


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


def test_metrics_start_date_excludes_stale_logs_and_judge_scores(tmp_path):
    judge_dir = tmp_path / ".exegol" / "optimizer_reports" / "judge_evals"
    judge_dir.mkdir(parents=True, exist_ok=True)
    (judge_dir / "judge_old-success.json").write_text(
        json.dumps({"score": 0}),
        encoding="utf-8",
    )

    _write_interaction_log(
        tmp_path,
        "old_success.json",
        "2026-05-30T23:59:59",
        "WatcherWedgeAgent",
        outcome="success",
        session_id="old-success",
    )
    _write_interaction_log(
        tmp_path,
        "old_failure.json",
        "2026-05-30T22:00:00",
        "WatcherWedgeAgent",
        outcome="failure",
        session_id="old-failure",
        errors=["old failure should not count"],
    )
    _write_interaction_log(
        tmp_path,
        "new_success.json",
        "2026-05-31T00:00:00",
        "WatcherWedgeAgent",
        outcome="success",
        session_id="new-success",
    )

    report = SuccessMetricsManager(str(tmp_path)).calculate_metrics(
        days=90,
        start_date="2026-05-31",
    )

    watcher = report["agent_breakdown"]["watcher_wedge"]
    assert report["fleet_aggregate"]["total_sessions"] == 1
    assert report["period_start"].startswith("2026-05-31T00:00:00")
    assert report["period_label"] == "Since 2026-05-31"
    assert watcher["total_sessions"] == 1
    assert watcher["bugs_introduced"] == 0
    assert watcher["recall"] == 1.0
    assert watcher["precision"] == 1.0
