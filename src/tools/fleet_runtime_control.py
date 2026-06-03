import json
import os
import subprocess
import threading
import time
from typing import Any, Dict, Iterable, List, Optional, Set
from urllib.parse import urlparse

import requests

from tools.egress_filter import EgressFilter


class FleetStopRequested(RuntimeError):
    """Raised inside autonomous work when the fleet has been stopped."""


_stop_event = threading.Event()
_lock = threading.Lock()
_known_ollama_models: Set[str] = set()
_last_stop: Dict[str, Any] = {}
_unload_thread: Optional[threading.Thread] = None


def request_runtime_stop(reason: str = "fleet stop requested") -> None:
    """Persistently pause autonomous runtime side effects until explicitly resumed."""
    with _lock:
        _last_stop.clear()
        _last_stop.update({
            "reason": reason,
            "requested_at": time.time(),
        })
        _stop_event.set()


def resume_runtime(reason: str = "fleet runtime resumed") -> None:
    with _lock:
        _last_stop.clear()
        _last_stop.update({
            "reason": reason,
            "resumed_at": time.time(),
        })
        _stop_event.clear()


def is_runtime_stopped() -> bool:
    return _stop_event.is_set()


def runtime_stop_reason() -> str:
    with _lock:
        return str(_last_stop.get("reason") or "fleet stop requested")


def raise_if_runtime_stopped(context: str = "") -> None:
    if is_runtime_stopped():
        reason = runtime_stop_reason()
        detail = f"{context}: {reason}" if context else reason
        raise FleetStopRequested(detail)


def register_ollama_model(model: Optional[str]) -> None:
    cleaned = _normalize_model_name(model)
    if not cleaned:
        return
    with _lock:
        _known_ollama_models.add(cleaned)


def known_ollama_models(extra: Optional[Iterable[str]] = None) -> List[str]:
    models: Set[str] = set()
    default_model = _normalize_model_name(os.getenv("OLLAMA_MODEL", "llama3"))
    if default_model:
        models.add(default_model)

    with _lock:
        models.update(_known_ollama_models)

    for model in _configured_agent_models():
        normalized = _normalize_model_name(model)
        if normalized:
            models.add(normalized)

    for model in extra or []:
        normalized = _normalize_model_name(model)
        if normalized:
            models.add(normalized)

    return sorted(models)


def unload_local_models_async(reason: str = "fleet stop requested", models: Optional[Iterable[str]] = None) -> None:
    """Ask local Ollama to release loaded models without blocking the stop endpoint."""
    if os.getenv("EXEGOL_DISABLE_LOCAL_MODEL_UNLOAD", "").lower() in {"1", "true", "yes"}:
        return
    global _unload_thread
    with _lock:
        if _unload_thread and _unload_thread.is_alive():
            return
        _unload_thread = threading.Thread(
            target=unload_local_models,
            kwargs={"reason": reason, "models": list(models or [])},
            daemon=True,
        )
        _unload_thread.start()


def unload_local_models(reason: str = "fleet stop requested", models: Optional[Iterable[str]] = None) -> List[Dict[str, Any]]:
    timeout_seconds = _float_env("EXEGOL_OLLAMA_UNLOAD_TIMEOUT_SECONDS", 2.0)
    targets = known_ollama_models(models)
    results: List[Dict[str, Any]] = []
    for model in targets:
        result = _ollama_stop_cli(model, timeout_seconds)
        if result.get("status") != "success":
            result = _ollama_keep_alive_unload(model, timeout_seconds)
        result["model"] = model
        result["reason"] = reason
        results.append(result)
        print(f"[FleetRuntime] Ollama unload {model}: {result.get('status')} ({result.get('mode')})")
    return results


def _normalize_model_name(model: Optional[str]) -> str:
    value = str(model or "").strip()
    if not value:
        return ""
    lowered = value.lower()
    if lowered == "ollama":
        return os.getenv("OLLAMA_MODEL", "llama3").strip()
    cloud_prefixes = (
        "anthropic",
        "claude",
        "gemini",
        "gpt-",
        "openai",
        "vllm",
        "llama.cpp",
    )
    if lowered.startswith(cloud_prefixes):
        return ""
    return value


def _configured_agent_models() -> List[str]:
    root = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
    config_path = os.path.join(root, "config", "agent_models.json")
    try:
        with open(config_path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception:
        return []
    if not isinstance(data, dict):
        return []
    return [str(value) for value in data.values() if value]


def _ollama_base_url() -> Optional[str]:
    api_url = os.getenv("OLLAMA_URL", "http://localhost:11434/api/generate")
    if not EgressFilter.is_url_allowed(api_url):
        return None
    parsed = urlparse(api_url)
    if not parsed.scheme or not parsed.netloc:
        return None
    return f"{parsed.scheme}://{parsed.netloc}"


def _ollama_stop_cli(model: str, timeout_seconds: float) -> Dict[str, Any]:
    try:
        result = subprocess.run(
            ["ollama", "stop", model],
            capture_output=True,
            text=True,
            timeout=timeout_seconds,
        )
    except FileNotFoundError:
        return {"status": "skipped", "mode": "cli", "detail": "ollama CLI not found"}
    except subprocess.TimeoutExpired:
        return {"status": "timeout", "mode": "cli", "detail": f"timed out after {timeout_seconds}s"}
    except Exception as exc:
        return {"status": "error", "mode": "cli", "detail": f"{type(exc).__name__}: {exc}"}

    if result.returncode == 0:
        return {"status": "success", "mode": "cli"}
    detail = (result.stderr or result.stdout or f"exit {result.returncode}").strip()
    return {"status": "error", "mode": "cli", "detail": detail[:300]}


def _ollama_keep_alive_unload(model: str, timeout_seconds: float) -> Dict[str, Any]:
    base_url = _ollama_base_url()
    if not base_url:
        return {"status": "skipped", "mode": "api", "detail": "Ollama URL is not allowed"}
    try:
        response = requests.post(
            f"{base_url}/api/generate",
            json={"model": model, "keep_alive": 0},
            timeout=timeout_seconds,
        )
        if response.status_code >= 400:
            return {
                "status": "error",
                "mode": "api",
                "detail": f"HTTP {response.status_code}: {response.text[:200]}",
            }
        return {"status": "success", "mode": "api"}
    except requests.Timeout:
        return {"status": "timeout", "mode": "api", "detail": f"timed out after {timeout_seconds}s"}
    except Exception as exc:
        return {"status": "error", "mode": "api", "detail": f"{type(exc).__name__}: {exc}"}


def _float_env(name: str, default: float) -> float:
    try:
        return max(0.1, float(os.getenv(name, str(default))))
    except (TypeError, ValueError):
        return default
