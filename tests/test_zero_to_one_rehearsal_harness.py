import json

from scripts.zero_to_one_rehearsal import run_rehearsal


def test_zero_to_one_rehearsal_writes_operator_evidence(tmp_path):
    report_path = tmp_path / "report.json"

    report = run_rehearsal(
        trials=1,
        max_cycles=6,
        work_dir=tmp_path / "rehearsal",
        report_path=report_path,
    )

    persisted = json.loads(report_path.read_text(encoding="utf-8"))
    trial = persisted["results"][0]
    assert report["success"] is True
    assert persisted["success"] is True
    assert persisted["trials_passed"] == 1
    assert trial["success"] is True
    assert trial["objective"]["phase"] == "done"
    assert trial["objective"]["last_agent_id"] == "uat_ulic"
    assert trial["uat_acceptance"]["status"] == "pass"
    assert all(trial["required_files"].values())
    assert trial["objective_event_count"] >= 5
