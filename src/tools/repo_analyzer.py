import os
import re
from typing import List, Dict

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
            
            # Skip registry files and the analyzer itself
            if "registry.py" in rel_path or "repo_analyzer.py" in rel_path:
                continue
                
            try:
                with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                    for i, line in enumerate(f, 1):
                        lower_line = line.lower()
                        
                        # Optimization: skip lines that definitely don't have our keywords
                        if not any(key in lower_line for key in patterns):
                            continue

                        # Skip lines that look like data (e.g. key-value pairs without comments)
                        # unless it's an explicit 'mock' keyword
                        is_comment = "#" in line or "//" in line
                        
                        for key, (label, category) in patterns.items():
                            if key in lower_line:
                                # Stricter requirement: word must appear in a comment or be 'mock'
                                is_mock = "mock" in lower_line and not is_comment
                                
                                # Ignore status assignments or string literals that aren't comments
                                # e.g. "status": "mock"
                                is_status_val = any(q + key + q in lower_line for q in ['"', "'"])
                                
                                if (is_comment or is_mock) and not is_status_val:
                                    findings.append({
                                        "task": f"Resolve {key.upper()} in {rel_path}:L{i}",
                                        "category": category,
                                        "context": line.strip(),
                                        "file_path": rel_path,
                                        "line_number": i
                                    })
                                    break # Only one finding per line
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
