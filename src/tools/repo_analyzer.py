import os
import re
from typing import List, Dict

# Regex: keyword must appear as a whole word (not embedded in prose like "demeanor" → skip)
_KEYWORD_WORD_RE = {
    key: re.compile(r'\b' + re.escape(key) + r'\b', re.IGNORECASE)
    for key in ("mock", "todo", "placeholder", "api_key", "credentials", "hardcoded")
}

# Prose phrases that contain keywords but are clearly documentation / system-prompt text
_FALSE_POSITIVE_PHRASES = (
    "identify mock",
    "identify the mock",
    "mock code",        # common in system prompt prose
    "mock integration",
    "no mock",
    "stub code",
    "hardcoded values",  # prose descriptions in docstrings
    "intolerant of weakness",
    "resolve mock",     # instructions about mocks, not a mock itself
    "mock findings",    # vibe_vader routing description
    "mock issues",
    "unhandled fetch calls and hardcoded",  # watcher wedge docstring
)

# Files whose own source code discusses detection patterns — always produce self-referential hits.
# These are excluded from scanning since they are the scanners, not the scanned.
_SELF_REFERENTIAL_FILES = {
    "repo_analyzer.py",
    "security_sabine_agent.py",
    "watcher_wedge_agent.py",
    "input_sanitizer.py",
}


def _is_inside_triple_quote_block(lines: list, current_idx: int) -> bool:
    """Returns True if the line at current_idx is inside a triple-quoted string."""
    triple_count = 0
    for idx in range(current_idx):
        triple_count += lines[idx].count('"""') + lines[idx].count("'''")
    # If odd number of triple-quotes before this line, we are inside a string
    return (triple_count % 2) == 1


def analyze_repository(repo_path: str, scan_path: str = "src") -> List[Dict]:
    """
    Scans the codebase for technical debt, mocks, placeholders, and missing credentials.
    
    Args:
        repo_path: Absolute path to the repository root.
        scan_path: Relative path from repo_root to start scanning.
        
    Returns:
        A list of findings, each containing:
        - task: A descriptive name of the issue.
        - category: 'mock' or 'limitation'.
        - context: Code snippet or reason.
        - file_path: Relative path to the file.
        - line_number: Line number where the issue was found.
    """
    findings = []
    patterns = {
        "mock": ("mock", "mock"),
        "todo": ("todo", "limitation"),
        "placeholder": ("placeholder", "limitation"),
        "api_key": ("api_key", "mock"),
        "credentials": ("credentials", "mock"),
        "hardcoded": ("hardcoded", "limitation")
    }
    
    full_scan_path = os.path.join(repo_path, scan_path)
    if not os.path.exists(full_scan_path):
        return []

    for root, _, files in os.walk(full_scan_path):
        for file in files:
            # Skip non-code files and common exclusions
            if file.endswith(('.json', '.md', '.txt', '.pyc', '.png', '.jpg', '.webp')):
                continue
            
            file_path = os.path.join(root, file)
            rel_path = os.path.relpath(file_path, repo_path)
            
            # Skip registry files, the analyzer itself, and self-referential scanner files
            if "registry.py" in rel_path or file in _SELF_REFERENTIAL_FILES:
                continue
                
            try:
                with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                    lines = f.readlines()

                # Track triple-quote depth for false-positive suppression
                triple_depth = 0

                for i, line in enumerate(lines, 1):
                    lower_line = line.lower().strip()
                    
                    # Track triple-quote state BEFORE processing this line
                    raw_line = lines[i - 1]
                    triple_depth += raw_line.count('"""') + raw_line.count("'''")
                    inside_triple_quote = (triple_depth % 2) == 1

                    # Optimization: skip lines that definitely don't have our keywords
                    if not any(key in lower_line for key in patterns):
                        continue

                    # Skip if this line is inside a multi-line string (system prompt prose, docstring, etc.)
                    # Exception: python single-line comments (#) inside triple-quote strings are rare,
                    # so we still allow comment lines through.
                    is_comment = "#" in line or "//" in line
                    if inside_triple_quote and not is_comment:
                        continue

                    # Skip lines that are false-positive prose (system prompts referencing mock code)
                    if any(phrase in lower_line for phrase in _FALSE_POSITIVE_PHRASES):
                        continue

                    for key, (label, category) in patterns.items():
                        if _KEYWORD_WORD_RE[key].search(lower_line):
                            # Ignore string literal value assignments — e.g. "status": "mock"
                            is_status_val = any(q + key + q in lower_line for q in ['"', "'"])
                            if is_status_val:
                                continue

                            # Allow: comment lines OR bare-word appearances in code (not prose)
                            if is_comment or (not inside_triple_quote):
                                findings.append({
                                    "task": f"Resolve {key.upper()} in {rel_path}:L{i}",
                                    "category": category,
                                    "context": line.strip(),
                                    "file_path": rel_path,
                                    "line_number": i
                                })
                                break  # Only one finding per line
            except Exception as e:
                # Silently skip files we can't read
                continue
    
    # Deduplicate results by task description
    unique_findings = []
    seen = set()
    for f in findings:
        if f["task"] not in seen:
            unique_findings.append(f)
            seen.add(f["task"])
            
    return unique_findings

if __name__ == "__main__":
    # Test execution
    import sys
    import io
    # Force UTF-8 output for windows terminals
    if sys.platform == "win32":
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
        
    repo = sys.argv[1] if len(sys.argv) > 1 else os.getcwd()
    results = analyze_repository(repo)
    for r in results:
        print(f"[{r['category'].upper()}] {r['task']} -> {r['context']}")
