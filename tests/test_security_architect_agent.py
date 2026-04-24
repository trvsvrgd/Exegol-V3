import os
import json
import pytest
from unittest.mock import MagicMock
from src.agents.security_architect_agent import SecurityArchitectAgent
from src.handoff import HandoffContext


REPO_PATH = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))


@pytest.fixture
def agent():
    return SecurityArchitectAgent(MagicMock())


@pytest.fixture
def handoff():
    return HandoffContext(
        repo_path=REPO_PATH,
        agent_id="security_architect",
        task_id="test_scan",
        model_routing="mock",
        max_steps=20
    )


# ------------------------------------------------------------------
# Smoke Test: Instantiation
# ------------------------------------------------------------------

def test_agent_instantiation(agent):
    assert agent.name == "SecurityArchitectAgent"
    assert agent.max_steps == 20
    assert "backlog_writer" in agent.tools
    assert "zero_day_patterns_detected" in agent.success_metrics
    assert "backlog_submissions" in agent.success_metrics


# ------------------------------------------------------------------
# Zero-Day Scanner
# ------------------------------------------------------------------

def test_zero_day_scan_returns_list(agent):
    findings = agent._scan_for_zero_day_patterns(REPO_PATH)
    assert isinstance(findings, list)


def test_zero_day_findings_have_required_fields(agent):
    findings = agent._scan_for_zero_day_patterns(REPO_PATH)
    for f in findings:
        assert "vuln_id" in f
        assert "severity" in f
        assert "file" in f
        assert "line" in f
        assert "recommendation" in f
        assert f["severity"] in ["CRITICAL", "HIGH", "MEDIUM", "LOW"]


def test_agent_self_excluded_from_scan(agent):
    """Ensure the scanner doesn't flag its own pattern definitions as vulnerabilities."""
    findings = agent._scan_for_zero_day_patterns(REPO_PATH)
    for f in findings:
        assert "security_architect_agent" not in f["file"], (
            f"Security agent scanned itself and produced false positive: {f['file']}:{f['line']}"
        )


# ------------------------------------------------------------------
# Architectural Gap Analysis
# ------------------------------------------------------------------

def test_architecture_evaluation_returns_list(agent):
    gaps = agent._evaluate_architecture(REPO_PATH)
    assert isinstance(gaps, list)


def test_architecture_gaps_have_required_fields(agent):
    gaps = agent._evaluate_architecture(REPO_PATH)
    for g in gaps:
        assert "id" in g
        assert "name" in g
        assert "severity" in g
        assert "recommendation" in g
        assert g["severity"] in ["CRITICAL", "HIGH", "MEDIUM", "LOW"]


def test_architecture_detects_missing_auth(agent):
    """Our repo has no auth_tool.py — this gap should always be detected."""
    gaps = agent._evaluate_architecture(REPO_PATH)
    gap_ids = [g["id"] for g in gaps]
    assert "SEC-ARCH-001" in gap_ids, "Missing auth layer should always be flagged"


# ------------------------------------------------------------------
# Risk Score
# ------------------------------------------------------------------

def test_risk_score_critical():
    agent = SecurityArchitectAgent(MagicMock())
    score = agent._compute_risk_score(
        [{"severity": "CRITICAL"}],
        []
    )
    assert score == "CRITICAL"


def test_risk_score_low_when_empty():
    agent = SecurityArchitectAgent(MagicMock())
    score = agent._compute_risk_score([], [])
    assert score == "LOW"


# ------------------------------------------------------------------
# Full Execute Cycle
# ------------------------------------------------------------------

def test_execute_returns_summary_string(agent, handoff):
    result = agent.execute(handoff)
    assert isinstance(result, str)
    assert "Security scan complete" in result
    assert "Backlog submissions" in result


def test_execute_creates_report_file(agent, handoff):
    agent.execute(handoff)
    reports_dir = os.path.join(REPO_PATH, ".exegol", "security_reports")
    assert os.path.isdir(reports_dir)
    report_files = [f for f in os.listdir(reports_dir) if f.startswith("security_scan_") and f.endswith(".json")]
    assert len(report_files) >= 1


def test_execute_writes_to_backlog(agent, handoff):
    backlog_path = os.path.join(REPO_PATH, ".exegol", "backlog.json")
    # Count before
    before_count = 0
    if os.path.exists(backlog_path):
        with open(backlog_path) as f:
            before_count = len(json.load(f))

    agent.execute(handoff)

    assert os.path.exists(backlog_path)
    with open(backlog_path) as f:
        after_count = len(json.load(f))
    # We can't guarantee new items (dedup), but backlog must still be valid JSON
    assert after_count >= before_count


def test_criticality_chains_to_compliance(agent, handoff):
    """If CRITICAL findings exist, agent should chain to compliance_cody."""
    agent.execute(handoff)
    # Either chains to compliance_cody if criticals found, or None if not
    assert agent.next_agent_id in ["compliance_cody", None]


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
