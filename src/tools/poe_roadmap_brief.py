import json
import os
import re
import sqlite3
from datetime import datetime
from typing import Any, Dict, List, Optional


BRIEF_PATH = ".exegol/roadmap_brief.json"
MAX_ACCOMPLISHED = 3
MAX_MVP_CRITERIA = 4
MAX_MVP_CONSTRAINTS = 3
MAX_LONG_TERM = 4


def load_or_build_poe_roadmap_brief(repo_path: str) -> Dict[str, Any]:
    """Return Poe's saved brief, or compute a deterministic fallback."""
    saved = _read_json(os.path.join(repo_path, BRIEF_PATH))
    if isinstance(saved, dict):
        normalized = _normalize_brief(saved)
        if normalized:
            return normalized
    return build_poe_roadmap_brief(repo_path, freshness="computed_fallback")


def save_poe_roadmap_brief(repo_path: str) -> Dict[str, Any]:
    """Refresh the durable brief after Product Poe changes planning state."""
    brief = build_poe_roadmap_brief(repo_path, freshness="poe_refreshed")
    path = os.path.join(repo_path, BRIEF_PATH)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(brief, f, indent=2)
    return brief


def build_poe_roadmap_brief(repo_path: str, freshness: str = "computed_fallback") -> Dict[str, Any]:
    repo_path = os.path.abspath(repo_path)
    objective = _load_objective(repo_path)
    exegol_roadmap = _read_text(os.path.join(repo_path, ".exegol", "roadmap.md"))
    root_roadmap = _read_text(os.path.join(repo_path, "ROADMAP.md"))
    active_backlog = _load_backlog_entries(repo_path, archived=False)
    archived_backlog = _load_backlog_entries(repo_path, archived=True)

    success_criteria = _dedupe(
        _clean_list(objective.get("success_criteria"))
        + _section_bullets(exegol_roadmap, "Poe-Defined Success Requirements")
    )[:MAX_MVP_CRITERIA]
    constraints = _dedupe(
        _clean_list(objective.get("constraints"))
        + [
            item
            for item in _section_bullets(exegol_roadmap, "Human Constraints")
            if item.lower() != "none specified."
        ]
    )[:MAX_MVP_CONSTRAINTS]

    long_term = _long_term_items(exegol_roadmap, root_roadmap, active_backlog)
    accomplished = _accomplished_items(objective, exegol_roadmap, root_roadmap, archived_backlog)

    goal = _clean_text(objective.get("goal"))
    mvp_summary = goal or _section_first_line(exegol_roadmap, "MVP") or "No MVP objective captured yet."
    brief = {
        "schema_version": 1,
        "owner_agent": "product_poe",
        "updated_at": _now(),
        "freshness": freshness,
        "objective": {
            "goal": goal,
            "phase": _clean_text(objective.get("phase")) or "idle",
            "status": _clean_text(objective.get("status")) or "idle",
            "loop_count": int(objective.get("loop_count", 0) or 0),
            "blocked_reason": _clean_text(objective.get("blocked_reason")) or None,
        },
        "current_focus": _current_focus(objective, active_backlog),
        "accomplished": accomplished[:MAX_ACCOMPLISHED],
        "mvp": {
            "summary": mvp_summary,
            "status": _mvp_status(objective),
            "success_criteria": success_criteria,
            "constraints": constraints,
        },
        "long_term": long_term[:MAX_LONG_TERM],
    }
    return brief


def _normalize_brief(brief: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    if brief.get("owner_agent") != "product_poe":
        return None
    objective = brief.get("objective") if isinstance(brief.get("objective"), dict) else {}
    mvp = brief.get("mvp") if isinstance(brief.get("mvp"), dict) else {}
    return {
        "schema_version": 1,
        "owner_agent": "product_poe",
        "updated_at": _clean_text(brief.get("updated_at")) or _now(),
        "freshness": _clean_text(brief.get("freshness")) or "poe_refreshed",
        "objective": {
            "goal": _clean_text(objective.get("goal")),
            "phase": _clean_text(objective.get("phase")) or "idle",
            "status": _clean_text(objective.get("status")) or "idle",
            "loop_count": int(objective.get("loop_count", 0) or 0),
            "blocked_reason": _clean_text(objective.get("blocked_reason")) or None,
        },
        "current_focus": _clean_text(brief.get("current_focus")) or "No roadmap objective captured yet.",
        "accomplished": _normalized_items(brief.get("accomplished"))[:MAX_ACCOMPLISHED],
        "mvp": {
            "summary": _clean_text(mvp.get("summary")) or "No MVP objective captured yet.",
            "status": _clean_text(mvp.get("status")) or "not_defined",
            "success_criteria": _clean_list(mvp.get("success_criteria"))[:MAX_MVP_CRITERIA],
            "constraints": _clean_list(mvp.get("constraints"))[:MAX_MVP_CONSTRAINTS],
        },
        "long_term": _normalized_items(brief.get("long_term"))[:MAX_LONG_TERM],
    }


def _load_objective(repo_path: str) -> Dict[str, Any]:
    objective = _read_json(os.path.join(repo_path, ".exegol", "objective.json"))
    if not isinstance(objective, dict):
        return {
            "id": None,
            "goal": "",
            "phase": "idle",
            "status": "idle",
            "loop_count": 0,
            "success_criteria": [],
            "constraints": [],
            "active_task_id": None,
            "blocked_reason": None,
        }
    phase = _clean_text(objective.get("phase")) or "idle"
    status = _clean_text(objective.get("status")) or ("blocked" if phase.startswith("blocked_") else "idle")
    return {
        "id": objective.get("id"),
        "goal": _clean_text(objective.get("goal")),
        "phase": phase,
        "status": status,
        "loop_count": int(objective.get("loop_count", 0) or 0),
        "success_criteria": _clean_list(objective.get("success_criteria")),
        "constraints": _clean_list(objective.get("constraints")),
        "active_task_id": objective.get("active_task_id"),
        "blocked_reason": _clean_text(objective.get("blocked_reason")) or None,
    }


def _load_backlog_entries(repo_path: str, archived: bool) -> List[Dict[str, Any]]:
    db_entries = _load_backlog_from_sqlite(repo_path, archived)
    if db_entries is not None:
        return db_entries

    filename = "backlog_archive.json" if archived else "backlog.json"
    data = _read_json(os.path.join(repo_path, ".exegol", filename))
    return data if isinstance(data, list) else []


def _load_backlog_from_sqlite(repo_path: str, archived: bool) -> Optional[List[Dict[str, Any]]]:
    db_path = os.path.abspath(os.path.join(repo_path, ".exegol", "backlog.db"))
    if not os.path.exists(db_path):
        return None
    uri = f"file:{db_path.replace(os.sep, '/')}?mode=ro"
    conn = None
    try:
        conn = sqlite3.connect(uri, uri=True)
        conn.row_factory = sqlite3.Row
        where = "archived_at IS NOT NULL" if archived else "archived_at IS NULL"
        rows = conn.execute(f"SELECT data FROM tasks WHERE {where} ORDER BY COALESCE(rank, 999999), created_at, id").fetchall()
        return [json.loads(row["data"]) for row in rows if row["data"]]
    except Exception:
        return None
    finally:
        if conn is not None:
            try:
                conn.close()
            except Exception:
                pass


def _accomplished_items(
    objective: Dict[str, Any],
    exegol_roadmap: str,
    root_roadmap: str,
    archived_backlog: List[Dict[str, Any]],
) -> List[Dict[str, str]]:
    items: List[Dict[str, str]] = []
    goal = _clean_text(objective.get("goal"))
    if goal and _clean_text(objective.get("phase")) == "done":
        items.append({"text": f"MVP objective verified done: {goal}", "evidence": "objective", "source_id": str(objective.get("id") or "")})

    for text, source_id in _checked_roadmap_items(exegol_roadmap, ".exegol/roadmap.md") + _checked_roadmap_items(root_roadmap, "ROADMAP.md"):
        items.append({"text": text, "evidence": "roadmap", "source_id": source_id})

    for task in archived_backlog:
        status = _clean_text(task.get("status")).lower()
        if status not in {"done", "completed"}:
            continue
        summary = _clean_text(task.get("summary"))
        if summary:
            items.append({"text": summary, "evidence": "completed_task", "source_id": _clean_text(task.get("id"))})

    return _dedupe_items(items)


def _long_term_items(exegol_roadmap: str, root_roadmap: str, active_backlog: List[Dict[str, Any]]) -> List[Dict[str, str]]:
    items = [
        {"text": item, "evidence": "roadmap", "source_id": ".exegol/roadmap.md"}
        for item in _section_bullets(exegol_roadmap, "Post-MVP Roadmap")
    ]

    for task in active_backlog:
        for item in _clean_list(task.get("post_mvp_roadmap")):
            items.append({"text": item, "evidence": "backlog", "source_id": _clean_text(task.get("id"))})

    for item in _root_future_roadmap_items(root_roadmap):
        items.append({"text": item, "evidence": "roadmap", "source_id": "ROADMAP.md"})

    return _dedupe_items(items)


def _current_focus(objective: Dict[str, Any], active_backlog: List[Dict[str, Any]]) -> str:
    blocked_reason = _clean_text(objective.get("blocked_reason"))
    if blocked_reason:
        return f"Blocked: {blocked_reason}"

    active_task_id = _clean_text(objective.get("active_task_id"))
    if active_task_id:
        task = next((item for item in active_backlog if _clean_text(item.get("id")) == active_task_id), None)
        if task and _clean_text(task.get("summary")):
            return f"Working on: {_clean_text(task.get('summary'))}"
        return f"Working on task: {active_task_id}"

    phase = _clean_text(objective.get("phase")).lower()
    if phase == "planning":
        return "Poe is shaping MVP requirements."
    if phase == "implementing":
        return "The MVP build is in progress."
    if phase in {"validating", "accepting"}:
        return "The MVP is under validation."
    if phase == "done":
        return "The MVP objective is complete."
    if phase == "failed_budget":
        return "The roadmap is paused by budget limits."
    if _clean_text(objective.get("goal")):
        return "Ready to plan MVP for the active objective."
    return "No roadmap objective captured yet."


def _mvp_status(objective: Dict[str, Any]) -> str:
    if not _clean_text(objective.get("goal")):
        return "not_defined"
    phase = _clean_text(objective.get("phase")).lower()
    status = _clean_text(objective.get("status")).lower()
    if phase == "done" or status == "done":
        return "done"
    if phase.startswith("blocked_") or status == "blocked":
        return "blocked"
    if phase == "failed_budget" or status == "failed":
        return "failed"
    if phase == "planning":
        return "planning"
    if phase == "implementing":
        return "building"
    if phase in {"validating", "accepting"}:
        return "validating"
    return "ready"


def _section_bullets(content: str, title: str) -> List[str]:
    section = _section_content(content, title)
    if not section:
        return []
    items = []
    for line in section.splitlines():
        cleaned = _clean_markdown_item(line)
        if cleaned:
            items.append(cleaned)
    return items


def _section_first_line(content: str, title: str) -> str:
    section = _section_content(content, title)
    if not section:
        return ""
    for line in section.splitlines():
        cleaned = _clean_markdown_item(line) or _clean_text(line)
        if cleaned:
            return cleaned
    return ""


def _section_content(content: str, title: str) -> str:
    match = re.search(
        rf"^##[^\n]*{re.escape(title)}[^\n]*\n(.*?)(?=^##|\Z)",
        content,
        re.DOTALL | re.MULTILINE | re.IGNORECASE,
    )
    return match.group(1) if match else ""


def _checked_roadmap_items(content: str, source_id: str) -> List[tuple[str, str]]:
    result = []
    for line in content.splitlines():
        if re.match(r"^\s*[-*]\s+\[[xX]\]\s+", line):
            item = _clean_markdown_item(line)
            if item:
                result.append((item, source_id))
    return result


def _root_future_roadmap_items(content: str) -> List[str]:
    sections = _future_sections(content)
    items: List[str] = []
    for section in sections:
        for line in section.splitlines():
            if re.match(r"^\s*[-*]\s+\[\s\]\s+", line):
                item = _clean_markdown_item(line)
                if item:
                    items.append(item)
    return items


def _future_sections(content: str) -> List[str]:
    matches = list(re.finditer(r"^(##+)\s+(.+?)\s*$", content, re.MULTILINE))
    result = []
    for index, match in enumerate(matches):
        title = match.group(2).lower()
        if not any(marker in title for marker in ("priority 1", "priority 2", "long", "product completeness")):
            continue
        start = match.end()
        end = matches[index + 1].start() if index + 1 < len(matches) else len(content)
        result.append(content[start:end])
    return result


def _clean_markdown_item(line: str) -> str:
    cleaned = re.sub(r"^\s*[-*]\s+\[[xX ]\]\s+", "", line)
    cleaned = re.sub(r"^\s*[-*]\s+", "", cleaned)
    cleaned = re.sub(r"^\s*\d+\.\s+", "", cleaned)
    return _clean_text(cleaned)


def _normalized_items(value: Any) -> List[Dict[str, str]]:
    if not isinstance(value, list):
        return []
    items = []
    for item in value:
        if not isinstance(item, dict):
            continue
        text = _clean_text(item.get("text"))
        if text:
            items.append({
                "text": text,
                "evidence": _clean_text(item.get("evidence")) or "roadmap",
                "source_id": _clean_text(item.get("source_id")),
            })
    return _dedupe_items(items)


def _dedupe_items(items: List[Dict[str, str]]) -> List[Dict[str, str]]:
    seen = set()
    result = []
    for item in items:
        text = _clean_text(item.get("text"))
        key = text.lower()
        if text and key not in seen:
            seen.add(key)
            result.append({
                "text": text,
                "evidence": _clean_text(item.get("evidence")) or "roadmap",
                "source_id": _clean_text(item.get("source_id")),
            })
    return result


def _dedupe(items: List[str]) -> List[str]:
    seen = set()
    result = []
    for item in items:
        cleaned = _clean_text(item)
        key = cleaned.lower()
        if cleaned and key not in seen:
            seen.add(key)
            result.append(cleaned)
    return result


def _clean_list(value: Any) -> List[str]:
    if not isinstance(value, list):
        return []
    return [_clean_text(item) for item in value if _clean_text(item)]


def _clean_text(value: Any) -> str:
    return " ".join(str(value or "").strip().split())


def _read_json(path: str) -> Any:
    if not os.path.exists(path):
        return None
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (OSError, json.JSONDecodeError):
        return None


def _read_text(path: str) -> str:
    if not os.path.exists(path):
        return ""
    try:
        with open(path, "r", encoding="utf-8") as f:
            return f.read()
    except OSError:
        return ""


def _now() -> str:
    return datetime.now().isoformat()
