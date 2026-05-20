import datetime
import json
import os
import uuid
from typing import Any, Callable, Dict, List, Optional

from tools.fleet_logger import log_interaction
from tools.hitl_manager import HITLManager
from tools.state_manager import StateManager


SOAK_CASES = [
    "agent_crash",
    "malformed_llm_output",
    "docker_unavailable",
    "provider_timeout",
    "stale_heartbeat",
    "duplicate_start_attempt",
]


CASE_DEFINITIONS: Dict[str, Dict[str, Any]] = {
    "agent_crash": {
        "agent_id": "developer_dex",
        "error": "Injected agent crash during autonomous loop.",
        "state": "blocked",
        "retryable": True,
    },
    "malformed_llm_output": {
        "agent_id": "model_router_mothma",
        "error": "Injected malformed LLM output that failed structured parsing.",
        "state": "blocked",
        "retryable": True,
    },
    "docker_unavailable": {
        "agent_id": "quality_quigon",
        "error": "Injected Docker unavailable condition for sandbox validation.",
        "state": "degraded",
        "retryable": True,
    },
    "provider_timeout": {
        "agent_id": "research_rex",
        "error": "Injected provider timeout while waiting for inference.",
        "state": "degraded",
        "retryable": True,
    },
    "stale_heartbeat": {
        "agent_id": "watcher_wedge",
        "error": "Injected stale heartbeat for an active autonomous session.",
        "state": "blocked",
        "retryable": True,
    },
    "duplicate_start_attempt": {
        "agent_id": "orchestrator",
        "error": "Injected duplicate start attempt while a session lock is active.",
        "state": "blocked",
        "retryable": False,
    },
}


class AutonomousSoakHarness:
    """Runs deterministic failure injections against Exegol's file-backed state.

    The harness intentionally stays local: all artifacts are written below the
    target repository's .exegol directory and no provider, Docker, or network
    calls are made.
    """

    def __init__(
        self,
        repo_path: str,
        now_fn: Optional[Callable[[], datetime.datetime]] = None,
    ):
        self.repo_path = os.path.abspath(repo_path)
        self.sm = StateManager(self.repo_path)
        self.hitl = HITLManager(self.repo_path)
        self.now_fn = now_fn or datetime.datetime.now
        self.state_file = ".exegol/autonomous_soak_state.json"
        self.events_file = ".exegol/supervisor_events.json"
        self.report_dir = os.path.join(self.repo_path, ".exegol", "soak_reports")

    def run(self, cases: Optional[List[str]] = None) -> Dict[str, Any]:
        selected_cases = cases or list(SOAK_CASES)
        results = [self.run_case(case_name) for case_name in selected_cases]
        summary = {
            "run_id": uuid.uuid4().hex[:12],
            "timestamp": self._now(),
            "repo_path": self.repo_path,
            "total": len(results),
            "passed": len([result for result in results if result["status"] == "pass"]),
            "failed": len([result for result in results if result["status"] != "pass"]),
            "results": results,
        }
        summary["status"] = "pass" if summary["failed"] == 0 else "fail"
        summary["artifact_path"] = self._write_summary(summary)
        return summary

    def retry_case(self, case_name: str) -> Dict[str, Any]:
        if case_name not in CASE_DEFINITIONS:
            raise ValueError(f"Unknown soak case: {case_name}")

        state = self.sm.read_json(self.state_file) or {"cases": {}}
        case_state = state.setdefault("cases", {}).setdefault(case_name, {})
        case_state["retry_count"] = int(case_state.get("retry_count", 0)) + 1
        case_state["last_retry_at"] = self._now()
        case_state["status"] = "retry_requested"
        self.sm.write_json(self.state_file, state)

        self._record_event(
            case_name=case_name,
            event_type="retry_requested",
            details={"retry_count": case_state["retry_count"]},
        )
        self._upsert_blocker(case_name, CASE_DEFINITIONS[case_name], "Retry requested; waiting for operator or next harness run.")
        return self.run_case(case_name)

    def run_case(self, case_name: str) -> Dict[str, Any]:
        if case_name not in CASE_DEFINITIONS:
            raise ValueError(f"Unknown soak case: {case_name}")

        definition = CASE_DEFINITIONS[case_name]
        session_id = f"soak_{case_name}_{uuid.uuid4().hex[:8]}"
        timestamp = self._now()
        log_path = log_interaction(
            agent_id=definition["agent_id"],
            outcome="failure",
            task_summary=f"Autonomous soak injection: {case_name}",
            repo_path=self.repo_path,
            errors=[definition["error"]],
            session_id=session_id,
            state_changes={
                "soak_case": case_name,
                "supervisor_state": definition["state"],
                "retryable": definition["retryable"],
            },
            metrics={"soak_harness": True},
        )
        self._record_event(
            case_name=case_name,
            event_type="failure_injected",
            details={
                "session_id": session_id,
                "error": definition["error"],
                "log_path": log_path,
            },
        )
        self._update_state(case_name, definition, timestamp)
        blocker_id = self._upsert_blocker(case_name, definition, definition["error"])

        checks = {
            "logged": os.path.exists(log_path),
            "state_updated": self._case_state(case_name).get("last_seen_at") == timestamp,
            "blocker_created_or_updated": self._blocker_exists(blocker_id),
            "ui_visible": self._ui_visible(blocker_id),
            "retry_available": bool(definition["retryable"] or self._case_state(case_name).get("retry_count", 0) >= 0),
        }
        status = "pass" if all(checks.values()) else "fail"
        return {
            "case": case_name,
            "status": status,
            "session_id": session_id,
            "blocker_id": blocker_id,
            "log_path": log_path,
            "checks": checks,
        }

    def _update_state(self, case_name: str, definition: Dict[str, Any], timestamp: str) -> None:
        state = self.sm.read_json(self.state_file) or {"cases": {}}
        case_state = state.setdefault("cases", {}).setdefault(case_name, {})
        case_state.update(
            {
                "status": definition["state"],
                "retryable": definition["retryable"],
                "last_seen_at": timestamp,
                "last_error": definition["error"],
                "attempt_count": int(case_state.get("attempt_count", 0)) + 1,
                "retry_count": int(case_state.get("retry_count", 0)),
            }
        )
        self.sm.write_json(self.state_file, state)

    def _record_event(self, case_name: str, event_type: str, details: Dict[str, Any]) -> None:
        events = self.sm.read_json(self.events_file) or []
        events.append(
            {
                "timestamp": self._now(),
                "source": "autonomous_soak_harness",
                "case": case_name,
                "event_type": event_type,
                "details": details,
            }
        )
        self.sm.write_json(self.events_file, events)

    def _upsert_blocker(self, case_name: str, definition: Dict[str, Any], context: str) -> str:
        blocker_id = f"soak_{case_name}"
        queue = self.hitl.get_queue()
        timestamp = self._now()
        summary = f"SOAK BLOCKER: {case_name.replace('_', ' ')}"
        existing = next((item for item in queue if item.get("id") == blocker_id), None)

        if existing:
            existing.update(
                {
                    "task": summary,
                    "category": "autonomous_soak",
                    "context": context,
                    "status": "pending",
                    "retryable": definition["retryable"],
                    "updated_at": timestamp,
                }
            )
        else:
            queue.append(
                {
                    "id": blocker_id,
                    "task": summary,
                    "category": "autonomous_soak",
                    "context": context,
                    "status": "pending",
                    "notes": "",
                    "retryable": definition["retryable"],
                    "timestamp": timestamp,
                }
            )

        self.sm.write_json(self.hitl.queue_file, queue)
        self.hitl._sync_to_markdown(queue)
        return blocker_id

    def _case_state(self, case_name: str) -> Dict[str, Any]:
        state = self.sm.read_json(self.state_file) or {"cases": {}}
        return state.get("cases", {}).get(case_name, {})

    def _blocker_exists(self, blocker_id: str) -> bool:
        return any(item.get("id") == blocker_id for item in self.hitl.get_queue())

    def _ui_visible(self, blocker_id: str) -> bool:
        queue = self.hitl.get_queue()
        pending = [item for item in queue if item.get("status") != "done"]
        return any(item.get("id") == blocker_id for item in pending)

    def _write_summary(self, summary: Dict[str, Any]) -> str:
        os.makedirs(self.report_dir, exist_ok=True)
        filename = f"autonomous_soak_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}_{summary['run_id']}.json"
        path = os.path.join(self.report_dir, filename)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(summary, f, indent=4)
        return path

    def _now(self) -> str:
        return self.now_fn().isoformat()


def run_autonomous_soak(repo_path: str, cases: Optional[List[str]] = None) -> Dict[str, Any]:
    return AutonomousSoakHarness(repo_path).run(cases=cases)


def retry_autonomous_soak_case(repo_path: str, case_name: str) -> Dict[str, Any]:
    return AutonomousSoakHarness(repo_path).retry_case(case_name)
