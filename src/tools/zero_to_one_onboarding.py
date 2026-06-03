import hashlib
import os
from typing import Any, Dict, List, Optional

from tools.backlog_manager import BacklogManager
from tools.hitl_manager import HITLManager
from tools.objective_manager import ObjectiveManager
from tools.thrawn_intel_manager import ThrawnIntelManager


IGNORED_DIRECTORIES = {
    ".exegol",
    ".git",
    ".github",
    ".idea",
    ".pytest_cache",
    ".vscode",
    "__pycache__",
    "node_modules",
}

LOW_SIGNAL_ROOT_FILES = {
    ".gitattributes",
    ".gitignore",
    "license",
    "license.md",
    "readme",
    "readme.md",
}

VADER_BOUNDARY_TASK = "Vader: Define non-negotiable demo boundaries"
ZERO_TO_ONE_TASK_ID = "zero_to_one_build"


def is_zero_to_one_repo(repo_path: str) -> bool:
    """Return True when a repo has no product content outside boilerplate."""
    if not os.path.isdir(repo_path):
        return False

    repo_root = os.path.abspath(repo_path)
    for current_root, dirnames, filenames in os.walk(repo_root):
        dirnames[:] = [
            dirname
            for dirname in dirnames
            if dirname not in IGNORED_DIRECTORIES
        ]

        rel_root = os.path.relpath(current_root, repo_root)
        for filename in filenames:
            rel_path = os.path.normpath(os.path.join(rel_root, filename))
            if _is_low_signal_file(rel_path):
                continue
            return False

    return True


def zero_to_one_status(repo_path: str) -> Dict[str, Any]:
    """Classify onboarding state for an empty repo."""
    if not is_zero_to_one_repo(repo_path):
        return {"action": "not_applicable"}
    if _has_actionable_backlog(repo_path):
        return {"action": "not_applicable"}

    intel = ThrawnIntelManager(repo_path).read_intent()
    objective = str(intel.get("objective") or "").strip()
    objective_record = ObjectiveManager(repo_path).load()
    objective_goal = str(objective_record.get("goal") or "").strip()
    questions = _valid_questions(intel.get("questions", []))
    unanswered_questions = [q for q in questions if not _answer(q)]
    pending_onboarding = _pending_onboarding_tasks(repo_path)
    answered_questions = [q for q in questions if _answer(q)]
    derived_objective = _derive_goal(intel, questions)

    if objective_goal:
        return {"action": "not_applicable"}

    if not objective and not questions and not pending_onboarding:
        return {
            "action": "kickoff",
            "summary": "Fresh repository has no captured intent. Start Thrawn/Vader onboarding.",
        }

    if not derived_objective and (unanswered_questions or pending_onboarding):
        return {
            "action": "wait",
            "summary": _wait_summary(unanswered_questions, pending_onboarding),
            "unanswered_questions": unanswered_questions,
            "pending_onboarding": pending_onboarding,
        }

    if derived_objective:
        return {
            "action": "activate",
            "summary": "Usable product intent is available. Seed the zero-to-one objective and let Poe refine the plan.",
            "unanswered_questions": unanswered_questions,
            "pending_onboarding": pending_onboarding,
            "answered_questions": answered_questions,
        }

    return {
        "action": "wait",
        "summary": "Waiting for a primary objective before starting autonomous build work.",
        "unanswered_questions": [],
        "pending_onboarding": [],
    }


def activate_zero_to_one_objective(repo_path: str) -> Optional[Dict[str, Any]]:
    """Create the durable objective from Thrawn/HITL context."""
    intel = ThrawnIntelManager(repo_path).read_intent()
    questions = _valid_questions(intel.get("questions", []))
    objective = _derive_goal(intel, questions)
    if not objective:
        return None

    constraints = _derive_constraints(intel, questions, repo_path)

    return ObjectiveManager(repo_path).create_or_update(
        goal=objective,
        success_criteria=[],
        constraints=constraints,
    )


def vader_onboarding_findings(repo_path: str) -> List[Dict[str, str]]:
    """Return Vader's one-time boundary prompt for zero-to-one repos."""
    if not is_zero_to_one_repo(repo_path):
        return []

    queue = HITLManager(repo_path).get_queue()
    if any(item.get("task") == VADER_BOUNDARY_TASK for item in queue):
        return []

    return [{
        "task": VADER_BOUNDARY_TASK,
        "category": "onboarding",
        "context": (
            "Before autonomous coding begins, state the build boundaries: game genre, "
            "allowed stack, asset/network limits, unacceptable shortcuts, and what must "
            "be visible in the live demo."
        ),
    }]


def build_zero_to_one_poe_plan(repo_path: str, objective: str) -> Dict[str, Any]:
    """Build Poe's deterministic MVP plan from the captured human context."""
    intel = ThrawnIntelManager(repo_path).read_intent()
    questions = _valid_questions(intel.get("questions", []))
    constraints = _derive_constraints(intel, questions, repo_path)
    success_criteria = _derive_success_criteria(objective, questions)
    post_mvp_roadmap = _derive_post_mvp_roadmap(objective, questions)
    return {
        "success_criteria": success_criteria,
        "constraints": constraints,
        "post_mvp_roadmap": post_mvp_roadmap,
        "rationale": _backlog_rationale(questions, constraints),
    }


def _is_low_signal_file(rel_path: str) -> bool:
    normalized = rel_path.replace("\\", "/")
    parts = [part for part in normalized.split("/") if part and part != "."]
    if not parts:
        return True

    if len(parts) == 1:
        return parts[0].lower() in LOW_SIGNAL_ROOT_FILES

    return False


def _valid_questions(questions: List[Any]) -> List[Dict[str, Any]]:
    return [
        q for q in questions
        if isinstance(q, dict) and str(q.get("question") or "").strip()
    ]


def _answer(question: Dict[str, Any]) -> str:
    answer = str(question.get("answer") or "").strip()
    return "" if answer.lower() == "pending" else answer


def _pending_onboarding_tasks(repo_path: str) -> List[Dict[str, Any]]:
    return [
        item for item in HITLManager(repo_path).get_pending()
        if str(item.get("category") or "").lower() == "onboarding"
    ]


def _has_actionable_backlog(repo_path: str) -> bool:
    actionable_statuses = {"todo", "backlogged", "pending_prioritization", "in_progress"}
    try:
        return any(
            str(task.get("status") or "").lower() in actionable_statuses
            for task in BacklogManager(repo_path).load_backlog()
        )
    except Exception as exc:
        print(f"[zero_to_one_onboarding] Failed to inspect backlog: {exc}")
        return False


def _wait_summary(unanswered_questions: List[Dict[str, Any]], pending_onboarding: List[Dict[str, Any]]) -> str:
    question_count = len(unanswered_questions)
    action_count = len(pending_onboarding)
    parts = []
    if question_count:
        parts.append(f"{question_count} Thrawn question(s)")
    if action_count:
        parts.append(f"{action_count} onboarding HITL action(s)")
    return "Waiting for human onboarding input before autonomous coding: " + ", ".join(parts) + "."


def _derive_goal(intel: Dict[str, Any], questions: List[Dict[str, Any]]) -> str:
    objective = str(intel.get("objective") or "").strip()
    if objective:
        return objective

    for question in questions:
        text = str(question.get("question") or "").lower()
        if any(marker in text for marker in ("primary objective", "main goal", "repository become", "elevator pitch")):
            answer = _answer(question)
            if answer:
                return answer

    for question in questions:
        answer = _answer(question)
        if answer:
            return answer

    return ""


def _derive_success_criteria(objective: str, questions: List[Dict[str, Any]]) -> List[str]:
    criteria = [
        "The repository contains a runnable application aligned with the stated objective.",
        "The app has enough polish and instructions to demo live from a fresh checkout.",
    ]
    objective_and_answers = " ".join([objective] + [_answer(q) for q in questions]).lower()
    if "game" in objective_and_answers:
        criteria.append("The game has a playable loop, clear controls, and visible win/lose or scoring feedback.")

    for question in questions:
        text = str(question.get("question") or "").lower()
        answer = _answer(question)
        if not answer:
            continue
        if any(marker in text for marker in ("success", "measure", "demo", "showcase")):
            criteria.append(answer)
        elif "target user" in text or "player" in text:
            criteria.append(f"Designed for: {answer}")

    return _dedupe(criteria)


def _derive_post_mvp_roadmap(objective: str, questions: List[Dict[str, Any]]) -> List[str]:
    objective_and_answers = " ".join([objective] + [_answer(q) for q in questions]).lower()
    roadmap = [
        "Automate browser-based UAT for the MVP acceptance path.",
        "Add lightweight telemetry for demo run completion, failures, and remediation attempts.",
        "Package the project with clearer setup checks for a fresh checkout.",
    ]
    if "game" in objective_and_answers:
        roadmap.extend([
            "Add more levels, difficulty tuning, and accessibility polish after the first playable loop is stable.",
            "Introduce optional audio and visual effects that still work without network access.",
        ])
    if len([q for q in questions if _answer(q)]) >= 4 or len(objective) > 120:
        roadmap.append("Split the roadmap into release slices after MVP validation captures enough execution data.")
    return _dedupe(roadmap)


def _derive_constraints(intel: Dict[str, Any], questions: List[Dict[str, Any]], repo_path: str) -> List[str]:
    constraints = [str(item).strip() for item in intel.get("architecture", []) if str(item).strip()]
    for question in questions:
        text = str(question.get("question") or "").lower()
        answer = _answer(question)
        if not answer:
            continue
        if any(marker in text for marker in ("constraint", "technical", "stack", "must use", "run on")):
            constraints.append(answer)

    for item in HITLManager(repo_path).get_queue():
        if item.get("task") == VADER_BOUNDARY_TASK and item.get("status") == "done" and item.get("notes"):
            constraints.append(f"Vader boundary: {item['notes']}")

    return _dedupe(constraints)


def _backlog_rationale(questions: List[Dict[str, Any]], constraints: List[str]) -> str:
    digest = hashlib.sha1(
        "\n".join([_answer(q) for q in questions] + constraints).encode("utf-8")
    ).hexdigest()[:8]
    answered = [
        f"- {q.get('question')}: {_answer(q)}"
        for q in questions
        if _answer(q)
    ]
    detail = "\n".join(answered) if answered else "No answered clarification questions were captured."
    if constraints:
        detail += "\nConstraints:\n" + "\n".join(f"- {item}" for item in constraints)
    return f"Seeded from zero-to-one onboarding ({digest}).\n{detail}"


def _dedupe(items: List[str]) -> List[str]:
    seen = set()
    result = []
    for item in items:
        cleaned = str(item).strip()
        key = cleaned.lower()
        if cleaned and key not in seen:
            seen.add(key)
            result.append(cleaned)
    return result
