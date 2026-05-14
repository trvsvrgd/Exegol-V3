"""
Tests for QualityQuigonAgent — validates the agent's core QA validation cycle,
metric calculation, and sandbox reporting logic.
"""
import os
import sys
import json
import shutil
import tempfile
import pytest
from unittest.mock import MagicMock, patch

# Add src to path for module resolution
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'src')))

from src.agents.quality_quigon_agent import QualityQuigonAgent
from src.handoff import HandoffContext


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

REPO_PATH = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))


def _make_mock_llm():
    """Return a mock LLM client that provides a stub system prompt."""
    client = MagicMock()
    client.generate_system_prompt.return_value = "You are QualityQuigon."
    return client


@pytest.fixture
def agent():
    return QualityQuigonAgent(_make_mock_llm())


@pytest.fixture
def handoff():
    return HandoffContext(
        repo_path=REPO_PATH,
        agent_id="quality_quigon",
        task_id="test_qa_cycle",
        model_routing="mock",
        max_steps=15
    )


@pytest.fixture
def sandbox_repo(tmp_path):
    """Creates a minimal repo structure with a sandbox for integration-style tests."""
    exegol_dir = tmp_path / ".exegol"
    sandboxes_dir = exegol_dir / "sandboxes"
    schemas_dir = exegol_dir / "schemas"
    os.makedirs(sandboxes_dir)
    os.makedirs(schemas_dir)

    # Master schema
    schema = {
        "$schema": "http://json-schema.org/draft-07/schema#",
        "type": "object",
        "required": ["app_name", "version", "architecture", "inference", "components"],
        "properties": {
            "app_name": {"type": "string"},
            "version": {"type": "string"},
            "architecture": {"type": "object"},
            "inference": {"type": "object", "required": ["provider", "base_model"]},
            "components": {"type": "array"}
        }
    }
    schema_path = schemas_dir / "app_schema.json"
    schema_path.write_text(json.dumps(schema))

    # One valid sandbox
    sb1 = sandboxes_dir / "sandbox_alpha"
    os.makedirs(sb1)
    app_json = {
        "app_name": "Alpha App",
        "version": "1.0.0",
        "architecture": {"diagram_type": "mermaid", "source": "README.md"},
        "inference": {"provider": "ollama", "base_model": "llama3"},
        "components": []
    }
    (sb1 / "app.exegol.json").write_text(json.dumps(app_json))

    return str(tmp_path)


# ---------------------------------------------------------------------------
# Smoke Tests: Instantiation
# ---------------------------------------------------------------------------

class TestQualityQuigonInstantiation:
    def test_agent_name(self, agent):
        assert agent.name == "QualityQuigonAgent"

    def test_max_steps(self, agent):
        assert agent.max_steps == 15

    def test_tools_registered(self, agent):
        expected = {"test_runner", "linter", "uat_sandbox", "sandbox_validator", "web_search"}
        assert expected.issubset(set(agent.tools))

    def test_success_metrics_initialized(self, agent):
        assert "repo_wide_health" in agent.success_metrics
        assert "sandbox_validation_coverage" in agent.success_metrics
        assert "schema_failure_rate" in agent.success_metrics
        assert "defect_escape_rate" in agent.success_metrics

    def test_all_metric_targets_set(self, agent):
        for metric_name, data in agent.success_metrics.items():
            assert "target" in data, f"Metric '{metric_name}' missing 'target'"
            assert "description" in data, f"Metric '{metric_name}' missing 'description'"


# ---------------------------------------------------------------------------
# _calculate_success_metrics
# ---------------------------------------------------------------------------

class TestCalculateSuccessMetrics:
    def test_returns_dict(self, agent):
        metrics = agent._calculate_success_metrics(REPO_PATH)
        assert isinstance(metrics, dict)

    def test_metric_keys_present(self, agent):
        metrics = agent._calculate_success_metrics(REPO_PATH)
        assert "repo_wide_health" in metrics
        assert "sandbox_validation_coverage" in metrics
        assert "schema_failure_rate" in metrics
        assert "defect_escape_rate" in metrics


# ---------------------------------------------------------------------------
# _log_validation_report
# ---------------------------------------------------------------------------

class TestLogValidationReport:
    def test_creates_markdown_report(self, agent, tmp_path):
        """Validation report should be written to .exegol/interaction_logs/."""
        fake_repo = str(tmp_path)
        results = ["Repo Infrastructure: pass", "State Regression: baseline_captured"]
        eval_res = {"status": "baseline_captured"}
        agent.regression_context = ""

        agent._log_validation_report(fake_repo, results, eval_res)

        logs_dir = tmp_path / ".exegol" / "interaction_logs"
        assert logs_dir.is_dir()
        md_files = list(logs_dir.glob("report_quigon_*.md"))
        assert len(md_files) >= 1

    def test_report_contains_results(self, agent, tmp_path):
        fake_repo = str(tmp_path)
        results = ["Unique marker: QUIGON_TEST_RESULT_XYZ"]
        eval_res = {"status": "pass"}
        agent.regression_context = ""

        agent._log_validation_report(fake_repo, results, eval_res)

        logs_dir = tmp_path / ".exegol" / "interaction_logs"
        md_files = list(logs_dir.glob("report_quigon_*.md"))
        content = md_files[0].read_text()
        assert "QUIGON_TEST_RESULT_XYZ" in content

    def test_report_includes_regression_context(self, agent, tmp_path):
        fake_repo = str(tmp_path)
        agent.regression_context = "Fleet state mismatch detected."
        results = []
        eval_res = {"status": "fail"}

        agent._log_validation_report(fake_repo, results, eval_res)

        logs_dir = tmp_path / ".exegol" / "interaction_logs"
        md_files = list(logs_dir.glob("report_quigon_*.md"))
        content = md_files[0].read_text()
        assert "Fleet state mismatch detected." in content


# ---------------------------------------------------------------------------
# Full Execute Cycle (mocked external tools)
# ---------------------------------------------------------------------------

class TestQualityQuigonExecute:
    @patch("src.tools.linter.run_lint")
    @patch("src.agents.quality_quigon_agent.run_regression_eval")
    @patch("src.agents.quality_quigon_agent.log_interaction")
    def test_execute_returns_string(self, mock_log, mock_eval, mock_lint, agent, handoff):
        mock_lint.return_value = {"status": "pass", "issues": []}
        mock_eval.return_value = {"status": "pass"}
        result = agent.execute(handoff)
        assert isinstance(result, str)
        assert "Validation Cycle complete" in result

    @patch("src.tools.linter.run_lint")
    @patch("src.agents.quality_quigon_agent.run_regression_eval")
    @patch("src.agents.quality_quigon_agent.log_interaction")
    def test_regression_fail_chains_to_dex(self, mock_log, mock_eval, mock_lint, agent, handoff):
        """A regression failure should set next_agent_id to developer_dex."""
        mock_lint.return_value = {"status": "pass", "issues": []}
        mock_eval.return_value = {"status": "fail", "saved": "abc", "current": "def"}
        agent.execute(handoff)
        assert agent.next_agent_id == "developer_dex"

    @patch("src.tools.linter.run_lint")
    @patch("src.agents.quality_quigon_agent.run_regression_eval")
    @patch("src.agents.quality_quigon_agent.log_interaction")
    def test_regression_pass_chains_to_uat_ulic(self, mock_log, mock_eval, mock_lint, agent, handoff):
        """A clean pass should chain to uat_ulic."""
        import dataclasses
        handoff = dataclasses.replace(handoff, task_id="fleet_cycle")  # skip archival branch
        mock_lint.return_value = {"status": "pass", "issues": []}
        mock_eval.return_value = {"status": "pass"}
        agent.execute(handoff)
        assert agent.next_agent_id == "uat_ulic"

    @patch("src.tools.linter.run_lint")
    @patch("src.agents.quality_quigon_agent.run_regression_eval")
    @patch("src.agents.quality_quigon_agent.log_interaction")
    def test_lint_failure_recorded_in_results(self, mock_log, mock_eval, mock_lint, agent, handoff):
        """When lint fails, the result summary should report infrastructure issues."""
        mock_lint.return_value = {"status": "fail", "issues": ["secrets.py:1 - Hardcoded key"]}
        mock_eval.return_value = {"status": "pass"}
        result = agent.execute(handoff)
        assert "fail" in result.lower() or "issue" in result.lower()

    @patch("src.tools.linter.run_lint")
    @patch("src.agents.quality_quigon_agent.run_regression_eval")
    @patch("src.agents.quality_quigon_agent.log_interaction")
    def test_scheduled_prompt_included_in_results(self, mock_log, mock_eval, mock_lint, agent, handoff):
        """If a scheduled_prompt is provided, it should appear in the result string."""
        import dataclasses
        handoff = dataclasses.replace(handoff, scheduled_prompt="Validate all sandboxes before deploy.")
        mock_lint.return_value = {"status": "pass", "issues": []}
        mock_eval.return_value = {"status": "pass"}
        result = agent.execute(handoff)
        assert "Targeted Validation" in result


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
