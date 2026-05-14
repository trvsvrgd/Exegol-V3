"""
Tests for src/tools/test_runner.py — the standardized test execution tool used by QualityQuigonAgent.
"""
import os
import shutil
import tempfile
import pytest
from unittest.mock import patch, MagicMock
from src.tools.test_runner import run_tests


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def temp_dir():
    d = tempfile.mkdtemp()
    yield d
    shutil.rmtree(d)


@pytest.fixture
def passing_test_dir(temp_dir):
    """A directory with a simple passing pytest file."""
    test_content = """
def test_always_passes():
    assert 1 + 1 == 2

def test_string_ops():
    assert "hello".upper() == "HELLO"
"""
    fpath = os.path.join(temp_dir, "test_sample.py")
    with open(fpath, "w") as f:
        f.write(test_content)
    return temp_dir


@pytest.fixture
def failing_test_dir(temp_dir):
    """A directory with a failing pytest file."""
    test_content = """
def test_always_fails():
    assert 1 == 2, "This test should always fail"
"""
    fpath = os.path.join(temp_dir, "test_failing.py")
    with open(fpath, "w") as f:
        f.write(test_content)
    return temp_dir


@pytest.fixture
def empty_test_dir(temp_dir):
    """A directory with no test files."""
    return temp_dir


# ---------------------------------------------------------------------------
# run_tests — top-level interface
# ---------------------------------------------------------------------------

class TestRunTests:
    def test_missing_path_returns_error(self):
        result = run_tests("/path/that/does/not/exist")
        assert result["status"] == "error"
        assert "not found" in result["message"].lower()

    def test_result_has_required_keys(self, temp_dir):
        result = run_tests(temp_dir)
        assert "status" in result
        assert "message" in result
        # exit_code and stdout/stderr only present on subprocess calls (not error early return)

    def test_passing_tests_return_pass(self, passing_test_dir):
        result = run_tests(passing_test_dir)
        assert result["status"] == "pass"
        assert result["exit_code"] == 0
        assert "PASSED" in result["stdout"] or result["status"] == "pass"

    def test_failing_tests_return_fail(self, failing_test_dir):
        result = run_tests(failing_test_dir)
        assert result["status"] == "fail"
        assert result["exit_code"] != 0

    def test_empty_dir_exits_cleanly(self, empty_test_dir):
        """pytest on a directory with no tests should not crash the tool."""
        result = run_tests(empty_test_dir)
        # pytest exits 5 (no tests collected) or 0; tool should handle both
        assert result["status"] in ("pass", "fail", "error")

    def test_stdout_captured(self, passing_test_dir):
        result = run_tests(passing_test_dir)
        assert "stdout" in result
        assert isinstance(result["stdout"], str)

    def test_stderr_captured(self, passing_test_dir):
        result = run_tests(passing_test_dir)
        assert "stderr" in result
        assert isinstance(result["stderr"], str)


# ---------------------------------------------------------------------------
# Timeout handling — mocked
# ---------------------------------------------------------------------------

class TestRunTestsTimeout:
    def test_timeout_returns_error(self, temp_dir):
        """Simulate a subprocess.TimeoutExpired and ensure graceful error return."""
        import subprocess
        with patch("src.tools.test_runner.subprocess.run",
                   side_effect=subprocess.TimeoutExpired(cmd="pytest", timeout=60)):
            result = run_tests(temp_dir)
        assert result["status"] == "error"
        assert "timed out" in result["message"].lower()

    def test_generic_exception_returns_error(self, temp_dir):
        """Simulate an unexpected exception during subprocess call."""
        with patch("src.tools.test_runner.subprocess.run",
                   side_effect=OSError("Mocked OS failure")):
            result = run_tests(temp_dir)
        assert result["status"] == "error"
        assert "execution error" in result["message"].lower()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
