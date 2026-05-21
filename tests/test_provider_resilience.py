from inference import llm_client
from inference.llm_client import LLMClient, TrackingLLMClient, classify_provider_failure


class FlakyClient(LLMClient):
    def __init__(self):
        super().__init__("flaky")
        self.calls = 0

    def generate(self, prompt, system_instruction=None, json_format=False):
        self.calls += 1
        if self.calls == 1:
            return "Gemini Error: timed out"
        return "ok"


class DownClient(LLMClient):
    def __init__(self):
        super().__init__("down")

    def generate(self, prompt, system_instruction=None, json_format=False):
        return "Anthropic Error: temporarily unavailable"


class LocalFallbackClient(LLMClient):
    def __init__(self, model=None):
        super().__init__(model or "local")

    def generate(self, prompt, system_instruction=None, json_format=False):
        return "local ok"


def test_provider_failures_are_classified_as_degraded_blockers():
    failure = classify_provider_failure("Gemini Error: timed out")

    assert failure["status"] == "degraded"
    assert failure["blocker_type"] == "provider_failure"
    assert failure["provider"] == "gemini"
    assert failure["retryable"] is True


def test_tracking_client_retries_retryable_provider_failure(monkeypatch):
    monkeypatch.setenv("EXEGOL_LLM_RETRY_ATTEMPTS", "2")
    monkeypatch.setenv("EXEGOL_LLM_RETRY_BACKOFF_SECONDS", "0")
    client = FlakyClient()

    response = TrackingLLMClient(client).generate("prompt")

    assert response == "ok"
    assert client.calls == 2


def test_tracking_client_can_fallback_to_local_provider(monkeypatch):
    monkeypatch.setenv("EXEGOL_LLM_RETRY_ATTEMPTS", "1")
    monkeypatch.setenv("EXEGOL_ENABLE_LOCAL_LLM_FALLBACK", "1")
    monkeypatch.setattr(llm_client, "OllamaClient", LocalFallbackClient)

    tracker = TrackingLLMClient(DownClient())
    response = tracker.generate("prompt")

    assert response == "local ok"
    assert any(event.get("event_type") == "provider_fallback" for event in tracker.history)
