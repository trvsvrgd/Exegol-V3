import os
from pathlib import Path
from typing import Dict, Iterable, List, Set


DEFAULT_IGNORE_NAMES = {
    ".git",
    ".venv",
    "__pycache__",
    "node_modules",
    "zzArchive",
}


def default_discovery_roots(project_root: str) -> List[Path]:
    roots: List[Path] = []
    configured = os.getenv("EXEGOL_REPO_DISCOVERY_ROOTS", "")
    if configured:
        roots.extend(Path(part).expanduser() for part in configured.split(os.pathsep) if part.strip())

    home = Path.home()
    python_projects = home / "Documents" / "Python_Projects"
    roots.append(python_projects)

    resolved_project = Path(project_root).resolve()
    if not python_projects.exists() and ".codex" not in resolved_project.parts:
        roots.append(resolved_project.parent)

    unique: List[Path] = []
    seen: Set[str] = set()
    for root in roots:
        resolved = root.resolve()
        key = os.path.normcase(str(resolved))
        if key not in seen:
            unique.append(resolved)
            seen.add(key)
    return unique


def is_managed_repo(path: Path) -> bool:
    return (path / ".git").exists() or (path / ".exegol").exists()


def discover_repositories(project_root: str, existing_paths: Iterable[str] = ()) -> List[Dict[str, object]]:
    existing = {os.path.normcase(os.path.abspath(path)) for path in existing_paths if path}
    discovered: List[Dict[str, object]] = []

    for root in default_discovery_roots(project_root):
        if not root.exists() or not root.is_dir():
            continue
        for child in sorted(root.iterdir(), key=lambda p: p.name.lower()):
            if not child.is_dir() or child.name in DEFAULT_IGNORE_NAMES or child.name.startswith("."):
                continue
            if not is_managed_repo(child):
                continue
            normalized = str(child.resolve())
            key = os.path.normcase(normalized)
            if key in existing:
                continue
            existing.add(key)
            discovered.append({
                "repo_path": normalized,
                "priority": 10,
                "model_routing_preference": "ollama",
                "agent_status": "idle",
                "max_steps_policy": 30,
                "requires_slack_approval_for_deletes": True,
                "daily_commit_routine": True,
            })

    return discovered


def sync_discovered_repositories(config: Dict[str, object], project_root: str) -> int:
    repos = config.setdefault("repositories", [])
    existing_paths = [repo.get("repo_path", "") for repo in repos if isinstance(repo, dict)]
    discovered = discover_repositories(project_root, existing_paths)
    repos.extend(discovered)
    return len(discovered)
