import argparse
import contextlib
import datetime
import json
import os
import sys
from pathlib import Path
from typing import Any, Dict, Iterator, List, Optional


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
for path in (str(ROOT), str(SRC)):
    if path not in sys.path:
        sys.path.insert(0, path)


class RehearsalLLM:
    """Deterministic local LLM stub for pre-demo zero-to-one rehearsals."""

    model = "zero-to-one-rehearsal"

    def generate(self, prompt, system_instruction=None, json_format=False):
        if "salvageable_ids" in prompt:
            return '{"salvageable_ids": []}'
        return "not json"

    def generate_system_prompt(self, agent):
        return f"Rehearsal system prompt for {getattr(agent, 'name', agent.__class__.__name__)}"


DEFAULT_ANSWERS = {
    "primary objective": "Build a browser puzzle game for the AI team demo.",
    "target user": "AI teammates watching a live knowledge-sharing session.",
    "technical constraints": "Use vanilla HTML, CSS, and JavaScript. No paid APIs or external assets.",
    "measure success": "The game runs locally, has a score, has restart, and shows a win or loss state.",
}


@contextlib.contextmanager
def isolated_rehearsal_runtime(work_dir: Path) -> Iterator[Any]:
    import agents.quality_quigon_agent as quality_quigon_agent
    import agents.thoughtful_thrawn_agent as thoughtful_thrawn_agent
    import agents.vibe_vader_agent as vibe_vader_agent
    import orchestrator as orchestrator_module
    import tools.agentic_coding as agentic_coding
    import tools.web_search as web_search_tool
    from inference.inference_manager import InferenceManager
    from orchestrator import ExegolOrchestrator

    work_dir.mkdir(parents=True, exist_ok=True)
    old_env = {key: os.environ.get(key) for key in [
        "EXEGOL_DISABLE_SCHEDULER",
        "EXEGOL_DISABLE_SLACK",
        "SLACK_BOT_TOKEN",
        "SLACK_APP_TOKEN",
        "SLACK_WEBHOOK_URL",
    ]}
    old_priority = orchestrator_module.PRIORITY_FILE_PATH
    old_history = orchestrator_module.HISTORY_FILE_PATH
    old_get_client = InferenceManager.__dict__["get_client"]
    old_setup_listener = orchestrator_module.slack_manager.setup_listener
    old_post_message = orchestrator_module.slack_manager.post_message
    old_web_searches = {
        "tools.web_search": web_search_tool.web_search,
        "tools.agentic_coding": agentic_coding.web_search,
        "agents.quality_quigon_agent": quality_quigon_agent.web_search,
        "agents.thoughtful_thrawn_agent": thoughtful_thrawn_agent.web_search,
        "agents.vibe_vader_agent": vibe_vader_agent.web_search,
    }

    os.environ["EXEGOL_DISABLE_SCHEDULER"] = "true"
    os.environ["EXEGOL_DISABLE_SLACK"] = "true"
    os.environ["SLACK_BOT_TOKEN"] = ""
    os.environ["SLACK_APP_TOKEN"] = ""
    os.environ["SLACK_WEBHOOK_URL"] = ""

    priority_file = work_dir / "priority.json"
    history_file = work_dir / "job_history.json"
    priority_file.write_text(
        json.dumps(
            {
                "repositories": [],
                "global_settings": {
                    "context_isolation": {
                        "enabled": True,
                        "fresh_instance_per_execution": True,
                        "max_handoff_depth": 8,
                        "log_every_session": True,
                    },
                    "compliance_monitoring": {},
                },
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    history_file.write_text("{}", encoding="utf-8")

    orchestrator_module.PRIORITY_FILE_PATH = str(priority_file)
    orchestrator_module.HISTORY_FILE_PATH = str(history_file)
    orchestrator_module.slack_manager.setup_listener = lambda _handler: None
    orchestrator_module.slack_manager.post_message = lambda *args, **kwargs: None
    InferenceManager.get_client = staticmethod(lambda provider=None, model=None: RehearsalLLM())
    web_search_tool.web_search = lambda *args, **kwargs: []
    agentic_coding.web_search = lambda *args, **kwargs: []
    quality_quigon_agent.web_search = lambda *args, **kwargs: []
    thoughtful_thrawn_agent.web_search = lambda *args, **kwargs: []
    vibe_vader_agent.web_search = lambda *args, **kwargs: []

    try:
        yield ExegolOrchestrator
    finally:
        orchestrator_module.PRIORITY_FILE_PATH = old_priority
        orchestrator_module.HISTORY_FILE_PATH = old_history
        orchestrator_module.slack_manager.setup_listener = old_setup_listener
        orchestrator_module.slack_manager.post_message = old_post_message
        InferenceManager.get_client = old_get_client
        web_search_tool.web_search = old_web_searches["tools.web_search"]
        agentic_coding.web_search = old_web_searches["tools.agentic_coding"]
        quality_quigon_agent.web_search = old_web_searches["agents.quality_quigon_agent"]
        thoughtful_thrawn_agent.web_search = old_web_searches["agents.thoughtful_thrawn_agent"]
        vibe_vader_agent.web_search = old_web_searches["agents.vibe_vader_agent"]
        for key, value in old_env.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value


def answer_onboarding(repo_path: Path, answers: Dict[str, str]) -> None:
    from tools.hitl_manager import HITLManager
    from tools.thrawn_intel_manager import ThrawnIntelManager
    from tools.zero_to_one_onboarding import VADER_BOUNDARY_TASK

    intel = ThrawnIntelManager(str(repo_path))
    current = intel.read_intent()
    for question in current.get("questions", []):
        text = str(question.get("question") or "")
        lowered = text.lower()
        answer = next(
            (value for marker, value in answers.items() if marker in lowered),
            "Keep the live demo small, local, and inspectable.",
        )
        intel.answer_question(text, answer)

    hitl = HITLManager(str(repo_path))
    for item in hitl.get_queue():
        if item.get("task") == VADER_BOUNDARY_TASK and item.get("status") != "done":
            hitl.resolve_task(
                item_id=item["id"],
                status="done",
                notes="Use a local browser app, no paid APIs, and no placeholder gameplay.",
            )


def collect_trial_result(repo_path: Path, trial_id: str, cycles_run: int) -> Dict[str, Any]:
    from tools.backlog_manager import BacklogManager
    from tools.objective_manager import ObjectiveManager

    objective = ObjectiveManager(str(repo_path)).load()
    required_files = ["index.html", "styles.css", "src/game.js", "README.md"]
    missing_files = [rel for rel in required_files if not (repo_path / rel).exists()]
    report_path = repo_path / ".exegol" / "uat_acceptance_report.json"
    acceptance_report = {}
    if report_path.exists():
        acceptance_report = json.loads(report_path.read_text(encoding="utf-8"))
    events_path = repo_path / ".exegol" / "objective_events.jsonl"
    event_count = len(events_path.read_text(encoding="utf-8").splitlines()) if events_path.exists() else 0
    active_backlog = [
        task for task in BacklogManager(str(repo_path)).load_backlog()
        if task.get("status") not in {"done", "completed", "archived", "dismissed"}
    ]

    success = (
        objective.get("phase") == "done"
        and objective.get("status") == "done"
        and objective.get("last_agent_id") == "uat_ulic"
        and acceptance_report.get("status") == "pass"
        and not missing_files
    )
    failures = []
    if objective.get("phase") != "done":
        failures.append(f"objective phase is {objective.get('phase')}, expected done")
    if objective.get("last_agent_id") != "uat_ulic":
        failures.append(f"last_agent_id is {objective.get('last_agent_id')}, expected uat_ulic")
    if acceptance_report.get("status") != "pass":
        failures.append("UAT acceptance report did not pass")
    if missing_files:
        failures.append(f"missing required files: {', '.join(missing_files)}")

    return {
        "trial_id": trial_id,
        "repo_path": str(repo_path),
        "success": success,
        "failures": failures,
        "cycles_run": cycles_run,
        "objective": objective,
        "uat_acceptance": acceptance_report,
        "required_files": {rel: (repo_path / rel).exists() for rel in required_files},
        "objective_event_count": event_count,
        "active_backlog_count": len(active_backlog),
    }


def run_trial(work_dir: Path, trial_index: int, max_cycles: int, answers: Dict[str, str]) -> Dict[str, Any]:
    from tools.repo_discovery import register_repository

    repo_path = work_dir / f"trial_{trial_index:02d}"
    (repo_path / ".git").mkdir(parents=True)

    with isolated_rehearsal_runtime(work_dir / f"runtime_{trial_index:02d}") as Orchestrator:
        orchestrator = Orchestrator()
        orchestrator.session_manager._get_agent_cooldown = lambda *_args, **_kwargs: 0.0
        register_repository(orchestrator.priority_config, str(repo_path), priority=1)
        orchestrator.save_config()
        orchestrator.load_config()

        cycles_run = 0
        orchestrator.run_fleet_cycle(repo_path=str(repo_path), include_due_scheduled=True, trigger_source="zero_to_one_rehearsal")
        cycles_run += 1
        answer_onboarding(repo_path, answers)

        for _ in range(max_cycles):
            orchestrator.run_fleet_cycle(repo_path=str(repo_path), include_due_scheduled=True, trigger_source="zero_to_one_rehearsal")
            cycles_run += 1
            result = collect_trial_result(repo_path, f"trial_{trial_index:02d}", cycles_run)
            if result["success"] or result["objective"].get("phase") in {"blocked_human", "failed_budget"}:
                return result

        return collect_trial_result(repo_path, f"trial_{trial_index:02d}", cycles_run)


def run_rehearsal(
    trials: int = 3,
    max_cycles: int = 8,
    work_dir: Optional[Path] = None,
    report_path: Optional[Path] = None,
    answers: Optional[Dict[str, str]] = None,
) -> Dict[str, Any]:
    stamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    work_dir = (work_dir or ROOT / "scratch" / f"zero_to_one_rehearsal_{stamp}").resolve()
    work_dir.mkdir(parents=True, exist_ok=True)
    answers = answers or DEFAULT_ANSWERS

    trial_results = [run_trial(work_dir, index + 1, max_cycles, answers) for index in range(trials)]
    success = all(result["success"] for result in trial_results)
    report = {
        "schema_version": 1,
        "generated_at": datetime.datetime.now().isoformat(),
        "success": success,
        "trials_requested": trials,
        "trials_passed": sum(1 for result in trial_results if result["success"]),
        "work_dir": str(work_dir),
        "results": trial_results,
    }

    report_path = (report_path or work_dir / "zero_to_one_rehearsal_report.json").resolve()
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    report["report_path"] = str(report_path)
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description="Run deterministic zero-to-one pre-demo rehearsal trials.")
    parser.add_argument("--trials", type=int, default=3)
    parser.add_argument("--max-cycles", type=int, default=8)
    parser.add_argument("--work-dir", type=Path, default=None)
    parser.add_argument("--report", type=Path, default=None)
    args = parser.parse_args()

    report = run_rehearsal(
        trials=args.trials,
        max_cycles=args.max_cycles,
        work_dir=args.work_dir,
        report_path=args.report,
    )
    print(json.dumps({
        "success": report["success"],
        "trials_passed": report["trials_passed"],
        "trials_requested": report["trials_requested"],
        "report_path": report["report_path"],
        "work_dir": report["work_dir"],
    }, indent=2))
    return 0 if report["success"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
