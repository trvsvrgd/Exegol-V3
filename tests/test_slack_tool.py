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


def test_slack_post_is_suppressed_when_fleet_runtime_stopped(tmp_path, monkeypatch):
    monkeypatch.setenv("EXEGOL_DISABLE_SLACK", "1")
    monkeypatch.setenv("EXEGOL_REPO_PATH", str(tmp_path))
    from tools.fleet_runtime_control import request_runtime_stop, resume_runtime

    SlackManager._instance = None
    manager = SlackManager()
    request_runtime_stop("unit test stop")

    try:
        result = manager.post_message("should not notify")
    finally:
        resume_runtime("test cleanup")

    assert result["status"] == "suppressed"
    assert result["mode"] == "fleet_stopped"
