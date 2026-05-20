import os
import sys
import time

os.environ["SLACK_BOT_TOKEN"] = ""
os.environ["SLACK_APP_TOKEN"] = ""
os.environ["SLACK_WEBHOOK_URL"] = ""
os.environ["EXEGOL_DISABLE_SCHEDULER"] = "true"

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

import api


def test_start_autonomous_is_idempotent(monkeypatch):
    api.stop_autonomous_fleet()

    calls = []

    def fake_run_fleet_cycle():
        calls.append(time.time())
        return True

    monkeypatch.setattr(api.orchestrator, "run_fleet_cycle", fake_run_fleet_cycle)

    first = api.start_autonomous_fleet()
    first_thread = api._continuous_fleet_thread
    second = api.start_autonomous_fleet()

    try:
        assert first["continuous_mode"] is True
        assert second["continuous_mode"] is True
        assert first_thread is api._continuous_fleet_thread
    finally:
        api.stop_autonomous_fleet()
