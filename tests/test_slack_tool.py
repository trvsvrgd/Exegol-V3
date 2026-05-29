from tools.slack_tool import SlackManager


def test_console_slack_fallback_does_not_shadow_time(tmp_path, monkeypatch):
    monkeypatch.setenv("EXEGOL_DISABLE_SLACK", "1")
    monkeypatch.setenv("EXEGOL_REPO_PATH", str(tmp_path))
    SlackManager._instance = None

    manager = SlackManager()
    result = manager.post_message("unit test console fallback")

    assert result["status"] == "success"
    assert result["mode"] == "console"
    assert result["ts"].startswith("console_")
