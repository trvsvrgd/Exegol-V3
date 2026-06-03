import json
import os
import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional

from tools.state_manager import StateManager


OBJECTIVE_PATH = ".exegol/objective.json"
OBJECTIVE_EVENTS_PATH = ".exegol/objective_events.jsonl"

VALID_PHASES = {
    "idle",
    "planning",
    "implementing",
    "validating",
    "accepting",
    "retrying",
    "remediating",
    "done",
    "blocked_human",
    "blocked_environment",
    "failed_budget",
}

VALID_STATUSES = {
    "idle",
    "running",
    "paused",
    "done",
    "blocked",
    "failed",
}

PHASE_STATUS = {
    "idle": "idle",
    "planning": "running",
    "implementing": "running",
    "validating": "running",
    "accepting": "running",
    "retrying": "running",
    "remediating": "running",
    "done": "done",
    "blocked_human": "blocked",
    "blocked_environment": "blocked",
    "failed_budget": "failed",
}

ALLOWED_TRANSITIONS = {
    "idle": {"planning", "blocked_human", "blocked_environment"},
    "planning": {"implementing", "blocked_human", "blocked_environment", "failed_budget", "idle"},
    "implementing": {"validating", "retrying", "remediating", "blocked_human", "blocked_environment", "failed_budget", "idle"},
    "validating": {"accepting", "done", "implementing", "planning", "retrying", "blocked_human", "blocked_environment", "failed_budget", "idle"},
    "accepting": {"done", "implementing", "validating", "retrying", "blocked_human", "blocked_environment", "failed_budget", "idle"},
    "retrying": {"implementing", "validating", "accepting", "remediating", "blocked_human", "blocked_environment", "failed_budget", "idle"},
    "remediating": {"retrying", "implementing", "validating", "accepting", "blocked_human", "blocked_environment", "failed_budget", "idle"},
    "blocked_human": {"planning", "implementing", "validating", "accepting", "idle", "failed_budget"},
    "blocked_environment": {"remediating", "retrying", "idle", "failed_budget"},
    "done": {"planning", "idle"},
    "failed_budget": {"planning", "idle"},
}

LOOP_COUNT_PHASES = {"planning", "implementing", "validating", "accepting", "retrying", "remediating"}
BLOCKED_PHASES = {"blocked_human", "blocked_environment"}
TERMINAL_PHASES = {"done", "failed_budget"}


class ObjectiveManager:
    """Owns the durable repo-local objective control-plane record."""

    def __init__(self, repo_path: str):
        self.repo_path = os.path.abspath(repo_path)
        self.sm = StateManager(self.repo_path)

    def load(self) -> Dict[str, Any]:
        objective = self.sm.read_json(OBJECTIVE_PATH)
        if not isinstance(objective, dict):
            objective = self._default_objective()
            self.save(objective, event_type="objective_initialized")
            return objective

        normalized = self._normalize(objective)
        if normalized != objective:
            self.save(normalized, event_type="objective_migrated")
        return normalized

    def create_or_update(
        self,
        goal: str,
        success_criteria: Optional[List[str]] = None,
        constraints: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        current = self.load()
        now = self._now()
        objective = {
            **current,
            "id": current.get("id") or f"objective_{uuid.uuid4().hex[:12]}",
            "repo_path": self.repo_path,
            "goal": goal.strip(),
            "success_criteria": self._clean_list(success_criteria),
            "constraints": self._clean_list(constraints),
            "phase": "idle",
            "active_task_id": current.get("active_task_id"),
            "status": "idle",
            "loop_count": int(current.get("loop_count", 0) or 0),
            "last_agent_id": current.get("last_agent_id"),
            "last_result": current.get("last_result"),
            "blocked_reason": None,
            "created_at": current.get("created_at") or now,
            "updated_at": now,
        }
        self.save(objective, event_type="objective_updated")
        return objective

    def transition(
        self,
        phase: str,
        status: Optional[str] = None,
        active_task_id: Optional[str] = None,
        last_agent_id: Optional[str] = None,
        last_result: Optional[Dict[str, Any]] = None,
        blocked_reason: Optional[str] = None,
    ) -> Dict[str, Any]:
        if phase not in VALID_PHASES:
            raise ValueError(f"Invalid objective phase: {phase}")

        objective = self.load()
        current_phase = objective.get("phase", "idle")
        self._validate_transition(current_phase, phase, blocked_reason)
        expected_status = PHASE_STATUS[phase]
        if status is not None and status != expected_status:
            if status == "paused" and expected_status == "running":
                expected_status = "paused"
            else:
                raise ValueError(f"Objective phase '{phase}' requires status '{expected_status}', got '{status}'")
        objective["phase"] = phase
        objective["status"] = expected_status
        if active_task_id is not None:
            objective["active_task_id"] = active_task_id
        if last_agent_id is not None:
            objective["last_agent_id"] = last_agent_id
        if last_result is not None:
            objective["last_result"] = last_result
        objective["blocked_reason"] = blocked_reason if phase in BLOCKED_PHASES else None
        if phase in TERMINAL_PHASES:
            objective["active_task_id"] = None
        objective["updated_at"] = self._now()
        if phase in LOOP_COUNT_PHASES:
            objective["loop_count"] = int(objective.get("loop_count", 0) or 0) + 1
        self.save(objective, event_type="objective_transition")
        return objective

    def can_transition(self, phase: str) -> bool:
        objective = self.load()
        current_phase = objective.get("phase", "idle")
        return phase in ALLOWED_TRANSITIONS.get(current_phase, set())

    def pause(self) -> Dict[str, Any]:
        objective = self.load()
        status = objective.get("status", "idle")
        if status == "running":
            objective["status"] = "paused"
            objective["updated_at"] = self._now()
            self.save(objective, event_type="objective_paused")
            return objective
        else:
            raise ValueError(f"Cannot pause objective: current status is '{status}', expected 'running'")

    def resume(self) -> Dict[str, Any]:
        objective = self.load()
        status = objective.get("status", "idle")
        if status == "paused":
            phase = objective.get("phase", "idle")
            expected_status = PHASE_STATUS.get(phase, "running")
            objective["status"] = expected_status
            objective["updated_at"] = self._now()
            self.save(objective, event_type="objective_resumed")
            return objective
        else:
            raise ValueError(f"Cannot resume objective: current status is '{status}', expected 'paused'")

    def save(self, objective: Dict[str, Any], event_type: str = "objective_saved") -> None:
        normalized = self._normalize(objective)
        self.sm.write_json(OBJECTIVE_PATH, normalized)
        self._append_event(event_type, normalized)

    def _default_objective(self) -> Dict[str, Any]:
        now = self._now()
        return {
            "schema_version": 1,
            "id": f"objective_{uuid.uuid4().hex[:12]}",
            "repo_path": self.repo_path,
            "goal": "",
            "success_criteria": [],
            "constraints": [],
            "phase": "idle",
            "active_task_id": None,
            "status": "idle",
            "loop_count": 0,
            "last_agent_id": None,
            "last_result": None,
            "blocked_reason": None,
            "created_at": now,
            "updated_at": now,
        }

    def _normalize(self, objective: Dict[str, Any]) -> Dict[str, Any]:
        now = self._now()
        phase = objective.get("phase") if objective.get("phase") in VALID_PHASES else "idle"
        expected_status = PHASE_STATUS.get(phase, "idle")
        status = objective.get("status")
        if status == "paused" and expected_status == "running":
            pass
        else:
            status = expected_status
        blocked_reason = objective.get("blocked_reason") if phase in BLOCKED_PHASES else None
        return {
            "schema_version": int(objective.get("schema_version", 1) or 1),
            "id": objective.get("id") or f"objective_{uuid.uuid4().hex[:12]}",
            "repo_path": os.path.abspath(objective.get("repo_path") or self.repo_path),
            "goal": str(objective.get("goal") or ""),
            "success_criteria": self._clean_list(objective.get("success_criteria")),
            "constraints": self._clean_list(objective.get("constraints")),
            "phase": phase,
            "active_task_id": objective.get("active_task_id"),
            "status": status,
            "loop_count": int(objective.get("loop_count", 0) or 0),
            "last_agent_id": objective.get("last_agent_id"),
            "last_result": objective.get("last_result"),
            "blocked_reason": blocked_reason,
            "created_at": objective.get("created_at") or now,
            "updated_at": objective.get("updated_at") or now,
        }

    def _append_event(self, event_type: str, objective: Dict[str, Any]) -> None:
        path = os.path.join(self.repo_path, OBJECTIVE_EVENTS_PATH)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        event = {
            "timestamp": self._now(),
            "event_type": event_type,
            "objective_id": objective.get("id"),
            "phase": objective.get("phase"),
            "status": objective.get("status"),
            "active_task_id": objective.get("active_task_id"),
            "last_agent_id": objective.get("last_agent_id"),
            "blocked_reason": objective.get("blocked_reason"),
        }
        with open(path, "a", encoding="utf-8") as f:
            f.write(json.dumps(event, sort_keys=True) + "\n")

    @staticmethod
    def _validate_transition(current_phase: str, next_phase: str, blocked_reason: Optional[str]) -> None:
        allowed = ALLOWED_TRANSITIONS.get(current_phase, set())
        if next_phase not in allowed:
            raise ValueError(f"Invalid objective transition: {current_phase} -> {next_phase}")
        if next_phase in BLOCKED_PHASES and not (blocked_reason or "").strip():
            raise ValueError(f"Objective phase '{next_phase}' requires a blocked_reason")

    @staticmethod
    def _clean_list(value: Optional[List[str]]) -> List[str]:
        if not value:
            return []
        return [str(item).strip() for item in value if str(item).strip()]

    @staticmethod
    def _now() -> str:
        return datetime.now().isoformat()
