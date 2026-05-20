import datetime

from orchestrator import ExegolOrchestrator


def make_orchestrator(tmp_path):
    orchestrator = ExegolOrchestrator.__new__(ExegolOrchestrator)
    orchestrator.active_target = {"repo_path": str(tmp_path)}
    orchestrator._should_stop_scheduler = False
    orchestrator.scheduler_state_file = ".exegol/scheduler_state.json"
    orchestrator.job_history_path = ".exegol/test_job_history.json"
    orchestrator.job_history = {}
    return orchestrator


def test_scheduler_state_persists_heartbeat(tmp_path):
    orchestrator = make_orchestrator(tmp_path)

    orchestrator._write_scheduler_state("healthy", detail="unit test", registered_jobs=2)

    data = (tmp_path / ".exegol" / "scheduler_state.json").read_text(encoding="utf-8")
    assert '"status": "healthy"' in data
    assert '"registered_jobs": 2' in data


def test_missed_job_startup_cap_records_skipped_events(tmp_path, monkeypatch):
    orchestrator = make_orchestrator(tmp_path)
    now = datetime.datetime.now()
    orchestrator.job_history = {
        "job1": (now - datetime.timedelta(days=1)).isoformat(),
        "job2": (now - datetime.timedelta(days=1)).isoformat(),
    }
    triggered = []
    monkeypatch.setattr(orchestrator, "_scheduled_trigger", lambda agent_id, summary, job_id=None: triggered.append(job_id))
    monkeypatch.setattr(orchestrator, "_save_job_history", lambda: None)

    orchestrator._check_for_missed_jobs({
        "global_settings": {"max_missed_jobs_on_startup": 1},
        "schedules": [
            {"id": "job1", "enabled": True, "frequency": "every_1_hours", "agent_id": "developer_dex", "summary": "one"},
            {"id": "job2", "enabled": True, "frequency": "every_1_hours", "agent_id": "developer_dex", "summary": "two"},
        ],
    })

    assert triggered == ["job1"]
    events = (tmp_path / ".exegol" / "scheduler_events.json").read_text(encoding="utf-8")
    assert "missed_job_skipped" in events
