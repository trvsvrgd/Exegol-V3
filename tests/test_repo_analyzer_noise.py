from tools.repo_analyzer import analyze_repository


def test_repo_analyzer_ignores_legitimate_secret_plumbing(tmp_path):
    src_dir = tmp_path / "src"
    src_dir.mkdir()
    (src_dir / "client.py").write_text(
        "\n".join(
            [
                "import os",
                "api_key = os.getenv('SERVICE_API_KEY')",
                "client = Service(api_key=api_key)",
                "headers={\"Authorization\": f\"Bearer {api_key}\"}",
            ]
        ),
        encoding="utf-8",
    )

    findings = analyze_repository(str(tmp_path))

    assert findings == []


def test_repo_analyzer_ignores_scanner_source_files(tmp_path):
    src_dir = tmp_path / "src" / "tools"
    src_dir.mkdir(parents=True)
    (src_dir / "linter.py").write_text(
        "issues.append('Warning: Potential hardcoded credential')\n",
        encoding="utf-8",
    )

    findings = analyze_repository(str(tmp_path))

    assert findings == []
