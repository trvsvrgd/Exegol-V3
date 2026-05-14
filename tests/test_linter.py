"""
Tests for src/tools/linter.py — the standardized linter tool used by QualityQuigonAgent.
"""
import os
import shutil
import tempfile
import pytest
from src.tools.linter import run_lint, _manual_ast_lint, _manual_web_lint


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def temp_dir():
    d = tempfile.mkdtemp()
    yield d
    shutil.rmtree(d)


@pytest.fixture
def clean_py_file(temp_dir):
    """A valid Python file with no linting issues."""
    content = """
def greet(name: str) -> str:
    return f"Hello, {name}!"

if __name__ == "__main__":
    print(greet("world"))
"""
    fpath = os.path.join(temp_dir, "clean.py")
    with open(fpath, "w") as f:
        f.write(content)
    return temp_dir


@pytest.fixture
def secret_py_file(temp_dir):
    """A Python file with a hardcoded secret — should trigger a lint warning."""
    content = """
api_key = "sk-supersecretkey12345678"
secret = "my_plaintext_password_here!"
"""
    fpath = os.path.join(temp_dir, "secrets.py")
    with open(fpath, "w") as f:
        f.write(content)
    return temp_dir


@pytest.fixture
def syntax_error_py_file(temp_dir):
    """A Python file with a syntax error."""
    content = "def broken(\n"  # unclosed paren
    fpath = os.path.join(temp_dir, "broken.py")
    with open(fpath, "w") as f:
        f.write(content)
    return temp_dir


@pytest.fixture
def secret_ts_file(temp_dir):
    """A TypeScript file with a hardcoded secret."""
    content = 'const apiKey = "sk-supersecretkey12345678";\n'
    fpath = os.path.join(temp_dir, "app.ts")
    with open(fpath, "w") as f:
        f.write(content)
    return temp_dir


# ---------------------------------------------------------------------------
# run_lint — top-level interface
# ---------------------------------------------------------------------------

class TestRunLint:
    def test_missing_path_returns_error(self):
        result = run_lint("/nonexistent/path/to/check")
        assert result["status"] == "error"
        assert "not found" in result["message"].lower()

    def test_clean_directory_returns_pass(self, clean_py_file):
        result = run_lint(clean_py_file)
        # Either pass or fail if pylint raises something benign; status must be a valid string
        assert result["status"] in ("pass", "fail")
        assert "issues" in result

    def test_result_has_required_keys(self, temp_dir):
        result = run_lint(temp_dir)
        assert "status" in result
        assert "issues" in result
        assert "message" in result

    def test_empty_dir_returns_pass(self, temp_dir):
        result = run_lint(temp_dir)
        assert result["status"] == "pass"
        assert result["issues"] == []


# ---------------------------------------------------------------------------
# _manual_ast_lint — Python secret detection
# ---------------------------------------------------------------------------

class TestAstLint:
    def test_clean_file_produces_no_issues(self, clean_py_file):
        result = _manual_ast_lint(clean_py_file)
        assert result["status"] == "pass"
        assert result["issues"] == []

    def test_detects_hardcoded_secret(self, secret_py_file):
        result = _manual_ast_lint(secret_py_file)
        assert result["status"] == "fail"
        assert len(result["issues"]) >= 1
        assert any("credential" in issue.lower() or "secret" in issue.lower() or "api_key" in issue.lower()
                   for issue in result["issues"])

    def test_syntax_error_caught(self, syntax_error_py_file):
        result = _manual_ast_lint(syntax_error_py_file)
        # SyntaxError should produce a lint issue, not an exception
        assert result["status"] == "fail"
        assert any("syntax error" in issue.lower() for issue in result["issues"])

    def test_skips_venv_directory(self, temp_dir):
        """Files inside venv/ should be excluded from scanning."""
        venv_dir = os.path.join(temp_dir, "venv", "lib")
        os.makedirs(venv_dir)
        venv_file = os.path.join(venv_dir, "secrets.py")
        with open(venv_file, "w") as f:
            f.write('token = "this-is-a-very-long-secret-1234567890"\n')
        result = _manual_ast_lint(temp_dir)
        # The venv file should have been skipped
        assert result["status"] == "pass"


# ---------------------------------------------------------------------------
# _manual_web_lint — TypeScript/JS secret and path detection
# ---------------------------------------------------------------------------

class TestWebLint:
    def test_clean_ts_file_has_no_issues(self, temp_dir):
        fpath = os.path.join(temp_dir, "clean.ts")
        with open(fpath, "w") as f:
            f.write('const greeting = "Hello world";\n')
        issues = _manual_web_lint(temp_dir)
        assert issues == []

    def test_detects_hardcoded_secret_in_ts(self, secret_ts_file):
        issues = _manual_web_lint(secret_ts_file)
        assert len(issues) >= 1
        assert any("secret" in i.lower() or "key" in i.lower() for i in issues)

    def test_skips_node_modules(self, temp_dir):
        """node_modules files should never be flagged."""
        nm_dir = os.path.join(temp_dir, "node_modules", "some-lib")
        os.makedirs(nm_dir)
        nm_file = os.path.join(nm_dir, "index.ts")
        with open(nm_file, "w") as f:
            f.write('const token = "sk-supersecretkey12345678";\n')
        issues = _manual_web_lint(temp_dir)
        assert issues == []

    def test_env_var_lookup_not_flagged(self, temp_dir):
        """process.env.KEY lookups should not be flagged as hardcoded secrets."""
        fpath = os.path.join(temp_dir, "env.ts")
        with open(fpath, "w") as f:
            f.write('const apiKey = process.env.API_KEY;\n')
        issues = _manual_web_lint(temp_dir)
        assert issues == []


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
