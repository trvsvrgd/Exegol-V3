import json
import os
import sys

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "src")))

from tools.autonomous_soak_harness import SOAK_CASES, AutonomousSoakHarness


def test_autonomous_soak_harness_writes_summary_and_blockers(tmp_path):
    harness = AutonomousSoakHarness(str(tmp_path))

    summary = harness.run()

    assert summary["status"] == "pass"
    assert summary["total"] == len(SOAK_CASES)
    assert summary["failed"] == 0
    assert os.path.exists(summary["artifact_path"])

    with open(summary["artifact_path"], "r", encoding="utf-8") as f:
        artifact = json.load(f)

    assert artifact["status"] == "pass"
    assert {result["case"] for result in artifact["results"]} == set(SOAK_CASES)
    for result in artifact["results"]:
        assert all(result["checks"].values())
        assert os.path.exists(result["log_path"])

    queue_path = tmp_path / ".exegol" / "user_action_required.json"
    queue = json.loads(queue_path.read_text(encoding="utf-8"))
    assert {item["id"] for item in queue if item["category"] == "autonomous_soak"} == {
        f"soak_{case_name}" for case_name in SOAK_CASES
    }

    events_path = tmp_path / ".exegol" / "supervisor_events.json"
    events = json.loads(events_path.read_text(encoding="utf-8"))
    assert len([event for event in events if event["event_type"] == "failure_injected"]) == len(SOAK_CASES)


def test_autonomous_soak_retry_updates_existing_blocker_without_duplicates(tmp_path):
    harness = AutonomousSoakHarness(str(tmp_path))

    first = harness.run(cases=["provider_timeout"])
    retry = harness.retry_case("provider_timeout")

    assert first["status"] == "pass"
    assert retry["status"] == "pass"

    state_path = tmp_path / ".exegol" / "autonomous_soak_state.json"
    state = json.loads(state_path.read_text(encoding="utf-8"))
    assert state["cases"]["provider_timeout"]["retry_count"] == 1
    assert state["cases"]["provider_timeout"]["attempt_count"] == 2

    queue_path = tmp_path / ".exegol" / "user_action_required.json"
    queue = json.loads(queue_path.read_text(encoding="utf-8"))
    soak_blockers = [item for item in queue if item["id"] == "soak_provider_timeout"]
    assert len(soak_blockers) == 1
    assert soak_blockers[0]["status"] == "pending"
    assert "updated_at" in soak_blockers[0]
