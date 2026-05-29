import datetime
import pytest

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
    assert '"enabled": true' in data
    assert '"heartbeat":' in data


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


def test_zero_missed_job_startup_cap_skips_all_events(tmp_path, monkeypatch):
    orchestrator = make_orchestrator(tmp_path)
    now = datetime.datetime.now()
    orchestrator.job_history = {
        "job1": (now - datetime.timedelta(days=1)).isoformat(),
    }
    triggered = []
    monkeypatch.setattr(orchestrator, "_scheduled_trigger", lambda agent_id, summary, job_id=None: triggered.append(job_id))
    monkeypatch.setattr(orchestrator, "_save_job_history", lambda: None)

    orchestrator._check_for_missed_jobs({
        "global_settings": {"max_missed_jobs_on_startup": 0},
        "schedules": [
            {"id": "job1", "enabled": True, "frequency": "every_1_hours", "agent_id": "developer_dex", "summary": "one"},
        ],
    })

    assert triggered == []
    events = (tmp_path / ".exegol" / "scheduler_events.json").read_text(encoding="utf-8")
    assert "missed_job_skipped" in events


def test_due_planner_supports_interval_daily_weekly_and_monthly_order(tmp_path):
    orchestrator = make_orchestrator(tmp_path)
    now = datetime.datetime(2026, 5, 29, 18, 30)
    orchestrator.job_history = {
        "hourly": "2026-05-29T16:00:00",
        "daily": "2026-05-28T10:01:00",
        "weekly": "2026-05-10T13:16:45",
        "monthly": "2026-04-10T13:16:45",
    }

    due = orchestrator.plan_due_scheduled_jobs(
        {
            "schedules": [
                {"id": "weekly", "enabled": True, "frequency": "friday", "at": "16:00", "agent_id": "report_revan", "summary": "weekly", "run_order": 30},
                {"id": "monthly", "enabled": True, "frequency": "monthly", "agent_id": "finance_fennec", "summary": "monthly", "run_order": 40},
                {"id": "daily", "enabled": True, "frequency": "daily", "at": "10:00", "agent_id": "vibe_vader", "summary": "daily", "run_order": 20},
                {"id": "hourly", "enabled": True, "frequency": "every_1_hour", "agent_id": "watcher_wedge", "summary": "hourly", "run_order": 10},
                {"id": "disabled", "enabled": False, "frequency": "daily", "at": "09:00", "agent_id": "vibe_vader", "summary": "disabled", "run_order": 1},
            ]
        },
        now=now,
        trigger_source="manual_run",
    )

    assert [job["id"] for job in due] == ["hourly", "daily", "weekly", "monthly"]
    assert all(job["due_reason"] for job in due)


def test_daily_due_detection_catches_prior_day_before_todays_run(tmp_path):
    orchestrator = make_orchestrator(tmp_path)
    orchestrator.job_history = {"daily": "2026-05-27T09:01:00"}

    due = orchestrator.plan_due_scheduled_jobs(
        {
            "schedules": [
                {"id": "daily", "enabled": True, "frequency": "daily", "at": "09:00", "agent_id": "vibe_vader", "summary": "daily"},
            ]
        },
        now=datetime.datetime(2026, 5, 29, 8, 0),
        trigger_source="manual_run",
    )

    assert [job["id"] for job in due] == ["daily"]


def test_manual_run_executes_due_scheduled_jobs_in_order(tmp_path, monkeypatch):
    orchestrator = make_orchestrator(tmp_path)
    now = datetime.datetime(2026, 5, 29, 18, 30)
    orchestrator.priority_config = {
        "repositories": [
            {
                "repo_path": str(tmp_path),
                "priority": 1,
                "agent_status": "idle",
                "model_routing_preference": "ollama",
            }
        ]
    }
    orchestrator.job_history = {
        "job_a": "2026-05-28T10:00:00",
        "job_b": "2026-05-28T10:00:00",
    }
    config = {
        "global_settings": {"enable_scheduler": True, "max_due_jobs_on_run_fleet": 1},
        "schedules": [
            {"id": "job_a", "enabled": True, "frequency": "every_1_hour", "agent_id": "watcher_wedge", "summary": "A", "run_order": 20},
            {"id": "job_b", "enabled": True, "frequency": "every_1_hour", "agent_id": "thoughtful_thrawn", "summary": "B", "run_order": 10},
        ],
    }
    calls = []
    events = []
    monkeypatch.setattr(orchestrator, "_load_cadence_config", lambda: config)
    monkeypatch.setattr(orchestrator, "_record_scheduler_event", lambda *args: events.append(args))
    monkeypatch.setattr(
        orchestrator,
        "_run_scheduled_task",
        lambda agent_id, summary, job_id=None, target=None: calls.append((job_id, agent_id, target["repo_path"])) or {"status": "completed", "job_id": job_id},
    )

    result = orchestrator.run_due_scheduled_agents(repo_path=str(tmp_path), now=now)

    assert calls == [("job_b", "thoughtful_thrawn", str(tmp_path))]
    assert result["due_count"] == 2
    assert result["triggered_count"] == 1
    assert any(event[0] == "manual_due_job_skipped" and event[1] == "job_a" for event in events)


def test_scheduler_disabled_by_env_writes_disabled_state(tmp_path, monkeypatch):
    orchestrator = make_orchestrator(tmp_path)
    states = []
    monkeypatch.setenv("EXEGOL_DISABLE_SCHEDULER_FOR_TESTS", "1")
    monkeypatch.setattr(orchestrator, "_write_scheduler_state", lambda status, detail="", registered_jobs=None: states.append((status, detail)))

    orchestrator._setup_cadence_engine()

    assert states == [("disabled", "disabled by EXEGOL_DISABLE_SCHEDULER_FOR_TESTS")]


def test_duplicate_scheduler_start_is_noop_with_healthy_state(tmp_path, monkeypatch):
    class RunningThread:
        def is_alive(self):
            return True

    orchestrator = make_orchestrator(tmp_path)
    orchestrator.scheduler_thread = RunningThread()
    states = []
    monkeypatch.delenv("EXEGOL_DISABLE_SCHEDULER_FOR_TESTS", raising=False)
    monkeypatch.setattr(orchestrator, "_write_scheduler_state", lambda status, detail="", registered_jobs=None: states.append((status, detail)))

    orchestrator._setup_cadence_engine()

    assert states == [("healthy", "scheduler already running")]


def test_shutdown_marks_scheduler_stopping_and_stops_monitors(tmp_path, monkeypatch):
    class SessionManagerStub:
        def __init__(self):
            self.shutdown_called = False

        def shutdown_monitors(self):
            self.shutdown_called = True

    orchestrator = make_orchestrator(tmp_path)
    orchestrator.session_manager = SessionManagerStub()
    states = []
    monkeypatch.setattr(orchestrator, "_write_scheduler_state", lambda status, detail="", registered_jobs=None: states.append((status, detail)))
    monkeypatch.setattr("orchestrator.time.sleep", lambda _seconds: None)

    with pytest.raises(SystemExit):
        orchestrator.shutdown()

    assert orchestrator._should_stop_scheduler is True
    assert orchestrator.is_running_fleet is False
    assert states == [("stopping", "orchestrator shutdown requested")]
    assert orchestrator.session_manager.shutdown_called is True
