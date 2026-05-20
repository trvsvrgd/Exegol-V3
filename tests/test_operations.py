from tools.operations import is_retry_allowed, redact_secret, upsert_blocker


def test_upsert_blocker_collapses_occurrences_and_preserves_type():
    queue = []

    first_id = upsert_blocker(
        queue,
        blocker_type="provider_failure",
        task="Provider outage",
        context="api_key=supersecretvalue123456789012",
        subject="gemini outage",
    )
    second_id = upsert_blocker(
        queue,
        blocker_type="provider_failure",
        task="Provider outage",
        context="token=anothersecretvalue1234567890",
        subject="gemini outage",
    )

    assert first_id == second_id
    assert len(queue) == 1
    assert queue[0]["blocker_type"] == "provider_failure"
    assert len(queue[0]["occurrences"]) == 2
    assert "[REDACTED]" in queue[0]["context"]


def test_retry_blocked_by_manual_hitl():
    queue = [{"status": "pending", "blocker_type": "manual_hitl"}]

    assert not is_retry_allowed(queue)


def test_redact_secret_dict_and_text():
    assert redact_secret({"api_key": "abc123456789012345678901234"})["api_key"] == "[REDACTED]"
    assert "abc123456789012345678901234" not in redact_secret("token=abc123456789012345678901234")
