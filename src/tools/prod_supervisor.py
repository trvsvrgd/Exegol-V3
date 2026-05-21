import datetime
import json
import os
import subprocess
from typing import Any, Callable, Dict, List, Optional

import requests

from tools.hitl_manager import HITLManager
from tools.operations import docker_health, normalize_blocker_type, upsert_blocker
from tools.state_manager import StateManager


AUTO_RESTARTABLE = {"backend", "frontend", "scheduler"}
REPORT_ONLY = {"docker", "session"}


class ProdSupervisor:
    """File-backed production supervisor health and remediation loop."""

    def __init__(
        self,
        repo_path: str,
        backend_probe: Optional[Callable[[], bool]] = None,
        frontend_probe: Optional[Callable[[], bool]] = None,
        scheduler_probe: Optional[Callable[[], bool]] = None,
        docker_probe: Optional[Callable[[], bool]] = None,
        restart_backend: Optional[Callable[[], bool]] = None,
        restart_frontend: Optional[Callable[[], bool]] = None,
        restart_scheduler: Optional[Callable[[], bool]] = None,
        now_fn: Optional[Callable[[], datetime.datetime]] = None,
        heartbeat_ttl_seconds: int = 120,
    ):
        self.repo_path = os.path.abspath(repo_path)
        self.sm = StateManager(self.repo_path)
        self.hitl = HITLManager(self.repo_path)
        self.backend_probe = backend_probe
        self.frontend_probe = frontend_probe
        self.scheduler_probe = scheduler_probe
        self.docker_probe = docker_probe
        self.restart_backend = restart_backend
        self.restart_frontend = restart_frontend
        self.restart_scheduler = restart_scheduler
        self.now_fn = now_fn or datetime.datetime.now
        self.heartbeat_ttl_seconds = heartbeat_ttl_seconds
        self.events_file = ".exegol/supervisor_events.json"
        self.state_file = ".exegol/supervisor_state.json"
        self.fleet_state_file = ".exegol/fleet_state.json"

    @classmethod
    def for_orchestrator(
        cls,
        repo_path: str,
        orchestrator: Any,
        backend_url: str = "http://localhost:8000/",
        frontend_url: str = "http://localhost:3000/",
    ) -> "ProdSupervisor":
        def scheduler_probe() -> bool:
            thread = getattr(orchestrator, "scheduler_thread", None)
            disabled = getattr(orchestrator, "_should_stop_scheduler", False)
            return bool(thread and thread.is_alive() and not disabled)

        def restart_scheduler() -> bool:
            if getattr(orchestrator, "_should_stop_scheduler", False):
                orchestrator._should_stop_scheduler = False
            orchestrator._setup_cadence_engine()
            thread = getattr(orchestrator, "scheduler_thread", None)
            return bool(thread and thread.is_alive())

        return cls(
            repo_path=repo_path,
            backend_probe=lambda: probe_http(backend_url),
            frontend_probe=lambda: probe_http(frontend_url),
            scheduler_probe=scheduler_probe,
            docker_probe=probe_docker,
            restart_scheduler=restart_scheduler,
        )

    def run_once(self) -> Dict[str, Any]:
        findings = []
        findings.extend(self._check_probe("backend", self.backend_probe))
        findings.extend(self._check_probe("frontend", self.frontend_probe))
        findings.extend(self._check_probe("scheduler", self.scheduler_probe))
        findings.extend(self._check_probe("docker", self.docker_probe))
        findings.extend(self._check_scheduler_heartbeat())
        findings.extend(self._check_stale_sessions())

        remediations = [self._remediate(finding) for finding in findings]
        self._reconcile_resolved_blockers(remediations)
        state = {
            "timestamp": self._now(),
            "status": "healthy" if not findings else "degraded",
            "findings": findings,
            "remediations": remediations,
            "components": self._component_summary(findings, remediations),
        }
        self.sm.write_json(self.state_file, state)
        self._write_fleet_state(state)
        return state

    def _check_probe(self, component: str, probe: Optional[Callable[[], bool]]) -> List[Dict[str, Any]]:
        if probe is None:
            return []
        try:
            healthy = bool(probe())
        except Exception as exc:
            healthy = False
            detail = str(exc)
        else:
            detail = "probe returned unhealthy" if not healthy else ""

        if healthy:
            self._record_event(component, "healthy", {"detail": "probe passed"})
            return []

        finding = {
            "component": component,
            "status": "dead" if component in AUTO_RESTARTABLE else "unavailable",
            "detail": detail,
            "auto_restartable": component in AUTO_RESTARTABLE,
            "blocker_type": self._blocker_type_for_component(component),
        }
        self._record_event(component, "unhealthy", finding)
        return [finding]

    def _check_stale_sessions(self) -> List[Dict[str, Any]]:
        heartbeat_dir = os.path.join(self.repo_path, ".exegol", "heartbeats")
        if not os.path.isdir(heartbeat_dir):
            return []

        findings = []
        now = self.now_fn()
        for filename in os.listdir(heartbeat_dir):
            if not filename.endswith(".json"):
                continue
            path = os.path.join(heartbeat_dir, filename)
            try:
                with open(path, "r", encoding="utf-8") as f:
                    heartbeat = json.load(f)
                if heartbeat.get("status") != "active":
                    continue
                last_pulse = datetime.datetime.fromisoformat(heartbeat.get("last_pulse", ""))
            except (OSError, ValueError, json.JSONDecodeError):
                continue

            age_seconds = (now - last_pulse).total_seconds()
            if age_seconds <= self.heartbeat_ttl_seconds:
                continue

            session_id = heartbeat.get("session_id", filename[:-5])
            finding = {
                "component": "session",
                "status": "stale",
                "session_id": session_id,
                "agent_id": heartbeat.get("agent_id", "unknown"),
                "detail": f"Heartbeat stale for {age_seconds:.0f}s",
                "age_seconds": round(age_seconds, 2),
                "auto_restartable": False,
                "blocker_type": "stale_heartbeat",
            }
            heartbeat["status"] = "stale"
            heartbeat["stale_detected_at"] = self._now()
            heartbeat["stale_age_seconds"] = round(age_seconds, 2)
            self.sm.write_json(os.path.join(".exegol", "heartbeats", filename), heartbeat)
            self._record_event("session", "stale_detected", finding)
            findings.append(finding)

        return findings

    def _check_scheduler_heartbeat(self) -> List[Dict[str, Any]]:
        state = self.sm.read_json(".exegol/scheduler_state.json")
        if not state or state.get("disabled"):
            return []
        try:
            heartbeat = datetime.datetime.fromisoformat(state.get("heartbeat", ""))
        except ValueError:
            return [{
                "component": "scheduler",
                "status": "stale",
                "detail": "scheduler heartbeat missing or invalid",
                "auto_restartable": True,
                "blocker_type": "stale_heartbeat",
            }]
        age_seconds = (self.now_fn() - heartbeat).total_seconds()
        if age_seconds <= self.heartbeat_ttl_seconds:
            return []
        return [{
            "component": "scheduler",
            "status": "stale",
            "detail": f"Scheduler heartbeat stale for {age_seconds:.0f}s",
            "age_seconds": round(age_seconds, 2),
            "auto_restartable": True,
            "blocker_type": "stale_heartbeat",
        }]

    def _remediate(self, finding: Dict[str, Any]) -> Dict[str, Any]:
        component = finding["component"]
        restart_fn = {
            "backend": self.restart_backend,
            "frontend": self.restart_frontend,
            "scheduler": self.restart_scheduler,
        }.get(component)

        if component in AUTO_RESTARTABLE and restart_fn is not None:
            try:
                restarted = bool(restart_fn())
            except Exception as exc:
                restarted = False
                detail = str(exc)
            else:
                detail = "restart succeeded" if restarted else "restart returned false"

            outcome = "recovered" if restarted else "blocked"
            self._record_event(component, outcome, {"finding": finding, "detail": detail})
            if not restarted:
                blocker_id = self._upsert_blocker(finding, detail)
            else:
                blocker_id = None
            return {
                "component": component,
                "action": "restart",
                "outcome": outcome,
                "detail": detail,
                "blocker_id": blocker_id,
            }

        reason = "auto restart not configured" if component in AUTO_RESTARTABLE else "manual remediation required"
        blocker_id = self._upsert_blocker(finding, reason)
        self._record_event(component, "blocked", {"finding": finding, "detail": reason})
        return {
            "component": component,
            "action": "report",
            "outcome": "blocked",
            "detail": reason,
            "blocker_id": blocker_id,
        }

    def _upsert_blocker(self, finding: Dict[str, Any], context: str) -> str:
        component = finding["component"]
        subject = finding.get("session_id", component)
        queue = self.hitl.get_queue()
        task = f"SUPERVISOR BLOCKER: {component} {finding['status']}"
        blocker_id = upsert_blocker(
            queue,
            blocker_type=finding.get("blocker_type") or self._blocker_type_for_component(component),
            task=task,
            context=f"{finding.get('detail', '')}. {context}".strip(),
            subject=f"{component}:{subject}",
            source="prod_supervisor",
        )
        for item in queue:
            if item.get("id") == blocker_id:
                item["supervisor_component"] = component
                break
        self.sm.write_json(self.hitl.queue_file, queue)
        self.hitl._sync_to_markdown(queue)
        return blocker_id

    def _reconcile_resolved_blockers(self, remediations: List[Dict[str, Any]]) -> None:
        active_blocked_components = {
            item.get("component")
            for item in remediations
            if item.get("outcome") == "blocked" and item.get("component")
        }
        queue = self.hitl.get_queue()
        changed = False
        now = self._now()

        for item in queue:
            if item.get("status") == "done":
                continue
            if item.get("source") != "prod_supervisor" or item.get("category") != "blocker":
                continue

            component = item.get("supervisor_component") or self._component_from_task(item.get("task", ""))
            if component in active_blocked_components:
                continue

            item["status"] = "done"
            item["completed_at"] = now
            item["notes"] = "Resolved by prod supervisor after health check recovered."
            changed = True
            self._record_event(component or "unknown", "blocker_resolved", {"blocker_id": item.get("id")})

        if changed:
            self.sm.write_json(self.hitl.queue_file, queue)
            self.hitl._sync_to_markdown(queue)

    def _component_from_task(self, task: str) -> Optional[str]:
        prefix = "SUPERVISOR BLOCKER: "
        if not task.startswith(prefix):
            return None
        remainder = task[len(prefix):].strip()
        return remainder.split(" ", 1)[0] if remainder else None

    def _blocker_type_for_component(self, component: str) -> str:
        return {
            "docker": "docker_unavailable",
            "session": "stale_heartbeat",
            "scheduler": "stale_heartbeat",
            "backend": "agent_crash",
            "frontend": "agent_crash",
        }.get(component, "manual_hitl")

    def _component_summary(self, findings: List[Dict[str, Any]], remediations: List[Dict[str, Any]]) -> Dict[str, Any]:
        summary: Dict[str, Any] = {
            "backend": {"status": "healthy"},
            "frontend": {"status": "healthy"},
            "docker": {"status": "healthy"},
            "scheduler": {"status": "healthy"},
            "autonomous_loop": {"status": "unknown"},
        }
        for finding in findings:
            component = finding.get("component")
            if component in summary:
                summary[component] = {
                    "status": "degraded",
                    "detail": finding.get("detail", ""),
                    "blocker_type": normalize_blocker_type(finding.get("blocker_type")),
                }
        for remediation in remediations:
            component = remediation.get("component")
            if component in summary:
                summary[component]["remediation"] = remediation.get("outcome")
                summary[component]["blocker_id"] = remediation.get("blocker_id")
        return summary

    def _write_fleet_state(self, supervisor_state: Dict[str, Any]) -> None:
        state = self.sm.read_json(self.fleet_state_file) or {}
        state.update({
            "schema_version": 1,
            "updated_at": self._now(),
            "process_state": supervisor_state.get("components", {}),
            "supervisor_status": supervisor_state.get("status"),
            "latest_blocker": next(
                (
                    item
                    for item in self.hitl.get_queue()
                    if item.get("status") != "done" and item.get("category") == "blocker"
                ),
                None,
            ),
        })
        self.sm.write_json(self.fleet_state_file, state)

    def _record_event(self, component: str, event_type: str, details: Dict[str, Any]) -> None:
        events = self.sm.read_json(self.events_file) or []
        events.append(
            {
                "timestamp": self._now(),
                "source": "prod_supervisor",
                "component": component,
                "event_type": event_type,
                "details": details,
            }
        )
        self.sm.write_json(self.events_file, events)

    def _now(self) -> str:
        return self.now_fn().isoformat()


def probe_http(url: str, timeout_seconds: float = 2.0) -> bool:
    try:
        response = requests.get(url, timeout=timeout_seconds)
        return response.status_code < 500
    except requests.RequestException:
        return False


def probe_docker(timeout_seconds: float = 5.0) -> bool:
    return docker_health(timeout_seconds=timeout_seconds)["status"] == "healthy"
