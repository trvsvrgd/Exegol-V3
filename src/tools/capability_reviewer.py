import os
import json
import glob
from typing import List, Dict, Any, Optional


# ---------------------------------------------------------------------------
# Core Mapping Functions
# ---------------------------------------------------------------------------

def map_requirement_to_capability(
    requirement: Dict[str, Any],
    capabilities: List[Dict[str, Any]],
    llm_client: Any = None
) -> Dict[str, Any]:
    """Maps a regulatory requirement to the most relevant system capability.

    Strategy:
    1. Exact ID match on 'required_capability_id' field.
    2. Keyword scan across capability name + description.
    3. Optional LLM semantic match (if llm_client is provided).
    """
    req_desc = requirement.get("description", "")
    req_summary = requirement.get("summary", "")
    target_id = requirement.get("required_capability_id")

    # 1. Exact ID match
    for cap in capabilities:
        if cap.get("id") == target_id:
            return {
                "matched": True,
                "capability": cap,
                "match_type": "exact_id",
                "confidence": 1.0,
                "reasoning": f"Exact ID match on '{target_id}'"
            }

    # 2. Keyword match (desc + summary → capability name + description)
    search_text = f"{req_summary} {req_desc}".lower()
    best_score = 0
    best_cap = None
    for cap in capabilities:
        cap_text = f"{cap.get('name', '')} {cap.get('description', '')}".lower()
        cap_words = set(cap_text.split())
        req_words = set(search_text.split())
        # Jaccard-style overlap
        overlap = len(cap_words & req_words)
        if overlap > best_score:
            best_score = overlap
            best_cap = cap

    if best_cap and best_score >= 3:
        return {
            "matched": True,
            "capability": best_cap,
            "match_type": "keyword",
            "confidence": min(0.5 + (best_score * 0.05), 0.85),
            "reasoning": f"Keyword overlap ({best_score} common terms) with capability '{best_cap['id']}'"
        }

    # 3. Semantic Match via LLM
    if llm_client:
        prompt = f"""
        Regulatory Requirement: {req_summary} - {req_desc}
        System Capabilities: {json.dumps(capabilities, indent=2)}

        Identify which system capability (if any) most closely addresses this requirement.
        Return a JSON object with:
        - 'matched': boolean
        - 'capability_id': string id or null
        - 'reasoning': string explaining the match or lack thereof
        - 'confidence': float 0.0-1.0
        """
        try:
            response = llm_client.generate(prompt, json_format=True)
            result = llm_client.parse_json_response(response)
            if result.get("matched") and result.get("capability_id"):
                for cap in capabilities:
                    if cap.get("id") == result["capability_id"]:
                        return {
                            "matched": True,
                            "capability": cap,
                            "match_type": "semantic",
                            "confidence": result.get("confidence", 0.5),
                            "reasoning": result.get("reasoning")
                        }
        except Exception as e:
            print(f"[capability_reviewer] LLM matching failed: {e}")

    return {
        "matched": False,
        "capability": None,
        "match_type": "none",
        "confidence": 0.0,
        "reasoning": "No matching capability found via ID, keyword, or semantic analysis."
    }


# ---------------------------------------------------------------------------
# Codebase Auto-Scanner
# ---------------------------------------------------------------------------

def scan_codebase_for_capabilities(repo_path: str) -> List[Dict[str, Any]]:
    """Auto-discovers system features by scanning the codebase structure.

    Walks src/tools/ and src/agents/ to build a live capability inventory
    derived from actual implemented modules, their docstrings, and filenames.
    This is used to keep system_capabilities.json accurate over time.

    Returns a list of discovered capability dicts (id, name, description, evidence).
    """
    discovered = []

    scan_dirs = [
        os.path.join(repo_path, "src", "tools"),
        os.path.join(repo_path, "src", "agents"),
    ]

    for scan_dir in scan_dirs:
        if not os.path.isdir(scan_dir):
            continue

        for filepath in glob.glob(os.path.join(scan_dir, "*.py")):
            filename = os.path.basename(filepath)
            if filename.startswith("_"):
                continue

            module_id = filename.replace(".py", "")
            docstring = _extract_module_docstring(filepath)
            relative_path = os.path.relpath(filepath, repo_path).replace("\\", "/")

            discovered.append({
                "id": module_id,
                "name": _id_to_readable_name(module_id),
                "description": docstring or f"Module: {module_id}",
                "evidence": relative_path,
                "implemented": True,
                "auto_discovered": True
            })

    return discovered


def _extract_module_docstring(filepath: str) -> Optional[str]:
    """Reads the first docstring from a Python file without importing it."""
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            lines = f.readlines()

        in_docstring = False
        docstring_lines = []
        quote_char = None

        for line in lines[:30]:  # Only scan top of file
            stripped = line.strip()
            if not in_docstring:
                if stripped.startswith('"""') or stripped.startswith("'''"):
                    quote_char = stripped[:3]
                    content = stripped[3:]
                    if content.endswith(quote_char) and len(content) > 3:
                        return content[:-3].strip()
                    in_docstring = True
                    if content:
                        docstring_lines.append(content)
            else:
                if quote_char and quote_char in stripped:
                    docstring_lines.append(stripped.split(quote_char)[0])
                    break
                docstring_lines.append(line.rstrip())

        if docstring_lines:
            return " ".join(docstring_lines).strip()[:200]
    except Exception:
        pass
    return None


def _id_to_readable_name(module_id: str) -> str:
    """Converts snake_case module IDs to Title Case readable names."""
    return " ".join(word.capitalize() for word in module_id.split("_"))


# ---------------------------------------------------------------------------
# Gap Analysis
# ---------------------------------------------------------------------------

def get_implemented_capabilities(capabilities: List[Dict[str, Any]]) -> List[str]:
    """Returns list of IDs for capabilities marked as implemented."""
    return [c["id"] for c in capabilities if c.get("implemented")]


def get_compliance_gaps(
    requirements: List[Dict[str, Any]],
    capabilities: List[Dict[str, Any]],
    llm_client: Any = None
) -> Dict[str, Any]:
    """Runs full gap analysis: maps every requirement to a capability and classifies results.

    Returns:
        {
            "covered": [...],       # requirements with a matched, implemented capability
            "gaps": [...],          # requirements with no match or unimplemented capability
            "coverage_pct": float,
            "total": int
        }
    """
    covered = []
    gaps = []

    for req in requirements:
        result = map_requirement_to_capability(req, capabilities, llm_client=llm_client)

        if result["matched"] and result["capability"] and result["capability"].get("implemented"):
            covered.append({
                "requirement": req,
                "capability": result["capability"],
                "match_type": result["match_type"],
                "confidence": result["confidence"],
                "reasoning": result.get("reasoning")
            })
        else:
            gaps.append({
                "requirement": req,
                "match_type": result["match_type"],
                "best_match": result.get("capability"),
                "reasoning": result.get("reasoning", "No match found")
            })

    total = len(requirements)
    coverage_pct = (len(covered) / total * 100) if total > 0 else 0.0

    return {
        "covered": covered,
        "gaps": gaps,
        "coverage_pct": round(coverage_pct, 1),
        "total": total
    }
