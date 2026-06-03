import pytest

from inference import llm_client
from inference.llm_client import LLMClient, OllamaClient, TrackingLLMClient, classify_provider_failure
from tools.fleet_runtime_control import FleetStopRequested, request_runtime_stop, resume_runtime


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


def test_ollama_generation_cancels_stream_and_requests_unload(monkeypatch):
    class FakeResponse:
        def __init__(self):
            self.closed = False

        def raise_for_status(self):
            return None

        def iter_lines(self, decode_unicode=True):
            yield '{"response": "partial"}'
            request_runtime_stop("unit stop during stream")
            yield '{"response": "late"}'

        def close(self):
            self.closed = True

    response = FakeResponse()
    unloads = []
    monkeypatch.setenv("OLLAMA_URL", "http://localhost:11434/api/generate")
    monkeypatch.setattr(llm_client.requests, "post", lambda *args, **kwargs: response)
    monkeypatch.setattr(llm_client, "unload_local_models_async", lambda reason, models=None: unloads.append((reason, models)))
    resume_runtime("test setup")

    try:
        with pytest.raises(FleetStopRequested):
            OllamaClient("qwen-test:latest").generate("prompt")
    finally:
        resume_runtime("test cleanup")

    assert response.closed is True
    assert unloads == [("fleet stop during Ollama generation", ["qwen-test:latest"])]
