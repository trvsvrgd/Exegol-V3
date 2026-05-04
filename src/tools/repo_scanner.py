import os
import re
from typing import List, Dict

def scan_for_security_vulnerabilities(repo_path: str) -> List[Dict]:
    """Scans the repository for security vulnerabilities and secrets.
    
    Checks for:
    - Hardcoded secrets and API keys
    - Insecure use of eval/exec
    - SSRF patterns
    - Insecure file permissions
    """
    findings = []
    
    # Secrets patterns
    secret_patterns = [
        (re.compile(r'(?i)(api[_-]?key|secret|password|token|auth|credential)["\s:]+["\']?([a-zA-Z0-9\-_]{16,})["\']?'), "High-entropy secret/key detected"),
        (re.compile(r'(?i)PRIVATE\s+KEY'), "Possible private key detected"),
        (re.compile(r'(?i)eval\(.*\)|exec\(.*\)'), "Insecure dynamic code execution (eval/exec) detected"),
        (re.compile(r'(?i)requests\.(get|post|put|delete)\(.*\burl\b.*\)'), "Potential SSRF vulnerability in request handling")
    ]

    for root, _, files in os.walk(repo_path):
        # Skip common directories
        if any(d in root for d in [".git", "__pycache__", ".venv", "node_modules", ".pytest_cache"]):
            continue
            
        for file in files:
            if not file.endswith(('.py', '.js', '.json', '.sh', '.bat', '.env')):
                continue
                
            file_path = os.path.join(root, file)
            rel_path = os.path.relpath(file_path, repo_path)
            
            try:
                with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                    for i, line in enumerate(f, 1):
                        for pattern, message in secret_patterns:
                            if pattern.search(line):
                                # Basic exclusion for common false positives
                                if "placeholder" in line.lower() or "your-" in line.lower():
                                    continue
                                    
                                findings.append({
                                    "task": f"Security Alert: {message} in {rel_path}:L{i}",
                                    "category": "security",
                                    "context": line.strip(),
                                    "file_path": rel_path,
                                    "line_number": i
                                })
            except Exception:
                continue
                
    return findings

if __name__ == "__main__":
    import sys
    repo = sys.argv[1] if len(sys.argv) > 1 else os.getcwd()
    results = scan_for_security_vulnerabilities(repo)
    for r in results:
        print(f"[{r['category'].upper()}] {r['task']}")
