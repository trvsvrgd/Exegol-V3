import hashlib
import os
import re
import subprocess
from datetime import datetime
from typing import Any, Dict, Iterable, List, Optional


BLOCKER_TYPES = {
    "agent_crash",
    "stale_heartbeat",
    "provider_failure",
    "docker_unavailable",
    "loop_guard",
    "schema_failure",
    "manual_hitl",
}

RETRYABLE_BLOCKER_TYPES = {"agent_crash", "provider_failure", "docker_unavailable", "stale_heartbeat"}
HITL_BLOCKER_TYPES = {"manual_hitl", "schema_failure", "loop_guard"}

SECRET_NAME_PATTERN = re.compile(r"(?i)(api[_-]?key|token|secret|password|authorization|bearer)")
SECRET_VALUE_PATTERN = re.compile(
    r"(?i)(api[_-]?key|token|secret|password|authorization|bearer)(['\"\s:=]+)([^'\"\s,;}]+)"
)
LONG_SECRET_PATTERN = re.compile(r"\b([A-Za-z0-9_\-]{24,})\b")


def normalize_blocker_type(value: Optional[str], default: str = "manual_hitl") -> str:
    if value in BLOCKER_TYPES:
        return value or default
    return default


def stable_blocker_id(blocker_type: str, subject: str) -> str:
    normalized = normalize_blocker_type(blocker_type)
    digest = hashlib.sha1(subject.encode("utf-8")).hexdigest()[:10]
    safe_subject = re.sub(r"[^A-Za-z0-9_\-]+", "_", subject).strip("_").lower()[:48]
    return f"blocker_{normalized}_{safe_subject or digest}_{digest}"


def redact_secret(value: Any) -> Any:
    if isinstance(value, dict):
        redacted: Dict[str, Any] = {}
        for key, item in value.items():
            if SECRET_NAME_PATTERN.search(str(key)):
                redacted[key] = "[REDACTED]"
            else:
                redacted[key] = redact_secret(item)
        return redacted
    if isinstance(value, list):
        return [redact_secret(item) for item in value]
    if not isinstance(value, str):
        return value

    redacted = SECRET_VALUE_PATTERN.sub(lambda match: f"{match.group(1)}{match.group(2)}[REDACTED]", value)
    return LONG_SECRET_PATTERN.sub("[REDACTED]", redacted)


def is_retry_allowed(queue: Iterable[Dict[str, Any]]) -> bool:
    for item in queue:
        if item.get("status") == "done":
            continue
        blocker_type = normalize_blocker_type(item.get("blocker_type"))
        if blocker_type in HITL_BLOCKER_TYPES:
            return False
    return True


def upsert_blocker(
    queue: List[Dict[str, Any]],
    *,
    blocker_type: str,
    task: str,
    context: str,
    subject: Optional[str] = None,
    priority: str = "critical",
    source: str = "operations",
) -> str:
    normalized_type = normalize_blocker_type(blocker_type)
    blocker_id = stable_blocker_id(normalized_type, subject or task)
    now = datetime.now().isoformat()
    sanitized_context = redact_secret(context)
    existing = next((item for item in queue if item.get("id") == blocker_id), None)

    occurrence = {
        "timestamp": now,
        "context": sanitized_context,
        "source": source,
    }
    payload = {
        "id": blocker_id,
        "task": redact_secret(task),
        "category": "blocker",
        "blocker_type": normalized_type,
        "context": sanitized_context,
        "priority": priority,
        "status": "pending",
        "notes": "",
        "timestamp": now,
        "source": source,
    }

    if existing:
        occurrences = existing.setdefault("occurrences", [])
        occurrences.append(occurrence)
        existing.update(payload)
        existing["updated_at"] = now
    else:
        payload["occurrences"] = [occurrence]
        payload["related_failures"] = []
        queue.append(payload)
    return blocker_id


def get_backend_process_state() -> Dict[str, Any]:
    pid = os.getpid()
    return {
        "name": "backend",
        "pid": pid,
        "status": "healthy",
        "timestamp": datetime.now().isoformat(),
    }


def docker_health(timeout_seconds: float = 5.0) -> Dict[str, Any]:
    try:
        result = subprocess.run(
            ["docker", "info"],
            capture_output=True,
            text=True,
            timeout=timeout_seconds,
        )
    except FileNotFoundError:
        return {"status": "unavailable", "detail": "docker executable not found"}
    except subprocess.TimeoutExpired:
        return {"status": "unavailable", "detail": "docker info timed out"}
    if result.returncode == 0:
        return {"status": "healthy", "detail": "docker daemon is responsive"}
    detail = (result.stderr or result.stdout or "docker info failed").strip()
    return {"status": "unavailable", "detail": redact_secret(detail)}


def audit_env_health(env: Optional[Dict[str, str]] = None) -> Dict[str, Any]:
    values = env if env is not None else os.environ
    required = ["EXEGOL_API_KEY"]
    optional = ["EXEGOL_HMAC_SECRET", "GEMINI_API_KEY", "ANTHROPIC_API_KEY", "OLLAMA_URL"]
    missing_required = [key for key in required if not values.get(key)]
    placeholders = [
        key
        for key in required + optional
        if values.get(key) and "your_" in str(values.get(key)).lower()
    ]
    return {
        "status": "healthy" if not missing_required and not placeholders else "degraded",
        "missing_required": missing_required,
        "placeholders": placeholders,
        "checked_keys": required + optional,
    }
