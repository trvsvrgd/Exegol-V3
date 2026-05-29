import argparse
import json
import shutil
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Iterable


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_WORKBENCH = ROOT / "workbench_ui"
REQUIRED_PACKAGES = ("next", "react", "react-dom")
NEXT_BUILTIN_GLOBAL_ERROR = Path("node_modules/next/dist/client/components/builtin/global-error.js")
CACHE_TARGETS = {
    "development": (Path(".next/dev"),),
    "production": (Path(".next"),),
}


def _read_json(path: Path) -> dict:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"{path} is not valid JSON: {exc}") from exc


def _resolve_inside(base: Path, target: Path) -> Path:
    base_resolved = base.resolve()
    target_resolved = target.resolve()
    try:
        target_resolved.relative_to(base_resolved)
    except ValueError as exc:
        raise ValueError(f"Refusing to touch path outside workbench_ui: {target_resolved}") from exc
    return target_resolved


def expected_package_versions(workbench: Path) -> dict[str, str]:
    lock_path = workbench / "package-lock.json"
    if not lock_path.exists():
        raise FileNotFoundError(f"Missing required lockfile: {lock_path}")

    lock = _read_json(lock_path)
    packages = lock.get("packages", {})
    expected: dict[str, str] = {}
    for package in REQUIRED_PACKAGES:
        version = packages.get(f"node_modules/{package}", {}).get("version")
        if not version:
            raise ValueError(f"package-lock.json does not pin node_modules/{package}")
        expected[package] = version
    return expected


def installed_package_versions(workbench: Path, packages: Iterable[str] = REQUIRED_PACKAGES) -> dict[str, str | None]:
    installed: dict[str, str | None] = {}
    for package in packages:
        package_json = workbench / "node_modules" / package / "package.json"
        if not package_json.exists():
            installed[package] = None
            continue
        installed[package] = str(_read_json(package_json).get("version") or "")
    return installed


def validate_frontend_install(workbench: Path = DEFAULT_WORKBENCH) -> list[str]:
    findings: list[str] = []
    if not workbench.exists():
        return [f"Missing workbench UI folder: {workbench}"]
    if not (workbench / "package.json").exists():
        findings.append(f"Missing package.json: {workbench / 'package.json'}")
    if not (workbench / "node_modules").exists():
        findings.append("node_modules is missing; run npm install in workbench_ui")
        return findings

    try:
        expected = expected_package_versions(workbench)
        installed = installed_package_versions(workbench)
    except (FileNotFoundError, ValueError) as exc:
        return [str(exc)]

    for package, expected_version in expected.items():
        installed_version = installed.get(package)
        if installed_version is None:
            findings.append(f"node_modules/{package} is missing; run npm install in workbench_ui")
        elif installed_version != expected_version:
            findings.append(
                f"node_modules/{package} is {installed_version}, expected {expected_version}; "
                "run npm install in workbench_ui"
            )

    if not (workbench / NEXT_BUILTIN_GLOBAL_ERROR).exists():
        findings.append(
            "Next.js built-in global-error artifact is missing from node_modules; "
            "run npm install in workbench_ui"
        )
    return findings


def repair_next_cache(workbench: Path = DEFAULT_WORKBENCH, mode: str = "production") -> list[Path]:
    removed: list[Path] = []
    for relative_target in CACHE_TARGETS[mode]:
        target = _resolve_inside(workbench, workbench / relative_target)
        if not target.exists():
            continue
        removed.append(remove_generated_path(target))
    return removed


def remove_generated_path(target: Path) -> Path:
    last_error: OSError | None = None
    for _attempt in range(4):
        try:
            if not target.exists():
                return target
            if target.is_symlink() or target.is_file():
                target.unlink()
            elif target.is_dir():
                shutil.rmtree(target)
            return target
        except OSError as exc:
            last_error = exc
            time.sleep(0.5)

    if target.exists():
        stale_name = f"{target.name}.stale-{datetime.now().strftime('%Y%m%d%H%M%S')}"
        stale_target = target.with_name(stale_name)
        try:
            target.rename(stale_target)
            return stale_target
        except OSError as exc:
            last_error = exc

    raise RuntimeError(f"Could not remove generated Next.js cache at {target}: {last_error}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate and repair the Exegol Workbench frontend startup state.")
    parser.add_argument("--workbench", default=str(DEFAULT_WORKBENCH))
    parser.add_argument("--mode", choices=sorted(CACHE_TARGETS), default="production")
    parser.add_argument("--repair-cache", action="store_true")
    args = parser.parse_args()

    workbench = Path(args.workbench)
    findings = validate_frontend_install(workbench)
    if findings:
        print("[FrontendCheck] BLOCKED")
        for finding in findings:
            print(f"- {finding}")
        return 1

    if args.repair_cache:
        try:
            removed = repair_next_cache(workbench, args.mode)
        except RuntimeError as exc:
            print("[FrontendCheck] BLOCKED")
            print(f"- {exc}")
            return 1
        if removed:
            for path in removed:
                print(f"[FrontendCheck] Removed generated Next.js cache: {path}")
        else:
            print("[FrontendCheck] No generated Next.js cache needed cleanup.")

    print("[FrontendCheck] Frontend install is ready.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
