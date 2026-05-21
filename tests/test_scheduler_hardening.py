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
