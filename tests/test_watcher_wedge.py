import json
from types import SimpleNamespace

from agents import watcher_wedge_agent
from agents.watcher_wedge_agent import WatcherWedgeAgent
from tools.repo_scanner import scan_for_security_vulnerabilities


def test_security_scanner_excludes_runtime_artifacts(tmp_path):
    runtime_dir = tmp_path / ".exegol" / "security_reports"
    runtime_dir.mkdir(parents=True)
    (runtime_dir / "old_scan.json").write_text(
        json.dumps([{"token": "a" * 32} for _ in range(1000)]),
        encoding="utf-8",
    )
    (tmp_path / "config.json").write_text('{"token": "abcdefghijklmnop"}\n', encoding="utf-8")

    findings = scan_for_security_vulnerabilities(str(tmp_path))

    assert len(findings) == 1
    assert findings[0]["file_path"] == "config.json"


def test_watcher_hands_health_report_to_product_poe(tmp_path, monkeypatch):
    monkeypatch.setattr(watcher_wedge_agent, "read_interaction_logs", lambda _repo, limit=100: [])
    monkeypatch.setattr(
        watcher_wedge_agent,
        "analyze_repository",
        lambda _repo: [{"task": "Resolve TODO in app.py:L1", "category": "limitation", "context": "# TODO"}],
    )
    monkeypatch.setattr(watcher_wedge_agent, "scan_for_security_vulnerabilities", lambda _repo: [])
    monkeypatch.setattr(WatcherWedgeAgent, "_targeted_code_scan", lambda self, _repo: [])
    monkeypatch.setattr(WatcherWedgeAgent, "_notify_slack", lambda self, _repo, _failures, _issues: None)
    monkeypatch.setattr(watcher_wedge_agent, "log_interaction", lambda **_kwargs: None)

    agent = WatcherWedgeAgent(llm_client=None)
    result = agent.execute(
        SimpleNamespace(
            repo_path=str(tmp_path),
            session_id="unit-session",
        )
    )

    assert agent.next_agent_id == "product_poe"
    assert "Handing off to product_poe" in result
    backlog = json.loads((tmp_path / ".exegol" / "backlog.json").read_text(encoding="utf-8"))
    assert backlog[0]["source_agent"] == "watcher_wedge"
    assert backlog[0]["type"] == "analysis"


def test_watcher_report_and_notification_are_ascii_safe(tmp_path, monkeypatch):
    posted_messages = []
    monkeypatch.setattr(watcher_wedge_agent, "post_to_slack", posted_messages.append)

    agent = WatcherWedgeAgent(llm_client=None)
    report = agent._generate_health_report(
        failures=[
            {
                "agent_id": "developer_dex",
                "task_summary": "stale heartbeat",
                "errors": ["timeout"],
            }
        ],
        audit_findings=[{"task": "Resolve TODO", "category": "limitation", "context": "# TODO"}],
        targeted_issues=[],
    )
    agent._notify_slack(str(tmp_path), fail_count=1, smell_count=1)

    report.encode("ascii")
    posted_messages[0].encode("ascii")
    assert "Operational Failures" in report
    assert "Watcher Wedge" in posted_messages[0]
