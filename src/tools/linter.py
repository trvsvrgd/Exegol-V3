import subprocess
import os
import ast
import re
import json
from typing import Dict, Any, List
from pathlib import Path

def run_lint(path: str) -> Dict[str, Any]:
    """
    Performs linting on the specified directory.
    Combines pylint/AST for Python and regex-based scanning for Web files (TSX/TS/JS).
    """
    if not os.path.exists(path):
        return {"status": "error", "message": f"Path not found: {path}"}
    
    results = {
        "status": "pass",
        "issues": [],
        "message": "Linting complete"
    }
    
    # 1. Python Linting (Pylint fallback to AST)
    py_results = _run_python_lint(path)
    if py_results["status"] == "fail":
        results["status"] = "fail"
        results["issues"].extend(py_results["issues"])

    # 2. Web/Frontend Linting (TSX, TS, JS)
    web_issues = _manual_web_lint(path)
    if web_issues:
        results["status"] = "fail"
        results["issues"].extend(web_issues)
    
    if results["status"] == "fail":
        results["message"] = f"Found {len(results['issues'])} issues"
        
    return results

from tools.fatal_error_router import check_and_route_terminal_output, route_fatal_error

def _run_python_lint(path: str) -> Dict[str, Any]:
    # Try to use pylint if available
    try:
        # Check if pylint is installed
        subprocess.run(["pylint", "--version"], capture_output=True, check=True)
        # Use a minimal config or just defaults
        command = f"pylint {path} --output-format=json --disable=all --enable=E,F,W0101,W0102"
        res = subprocess.run(
            ["pylint", path, "--output-format=json", "--disable=all", "--enable=E,F,W0101,W0102"],
            capture_output=True,
            text=True
        )
        
        # Always route terminal errors with 'FATAL' to the Exegol Fleet
        check_and_route_terminal_output(path, res.stdout, res.stderr, command)
        
        if res.returncode != 0 and res.stdout:
            try:
                pylint_issues = json.loads(res.stdout)
                issues = [f"{issue['path']}:{issue['line']} - {issue['message']}" for issue in pylint_issues]
                return {"status": "fail", "issues": issues}
            except:
                pass
        
        # If pylint fails or returns nothing useful, fallback to AST for secrets
        return _manual_ast_lint(path)
    except (subprocess.CalledProcessError, FileNotFoundError) as e:
        error_msg = str(e)
        if "FATAL" in error_msg:
             route_fatal_error(path, error_msg)
        return _manual_ast_lint(path)
    except Exception as e:
        error_msg = str(e)
        if "FATAL" in error_msg:
             route_fatal_error(path, error_msg)
        return _manual_ast_lint(path)

def _manual_ast_lint(path: str) -> Dict[str, Any]:
    root = Path(path)
    issues = []
    
    for py_file in root.rglob("*.py"):
        if "node_modules" in str(py_file) or "venv" in str(py_file) or ".exegol" in str(py_file):
            continue
        try:
            with open(py_file, "r", encoding="utf-8") as f:
                content = f.read()
                try:
                    tree = ast.parse(content)
                except SyntaxError as se:
                    issues.append(f"{py_file.name}:{se.lineno} - Syntax Error: {se.msg}")
                    continue
                
                for node in ast.walk(tree):
                    # 1. Hardcoded Credentials
                    if isinstance(node, ast.Assign):
                        for target in node.targets:
                            if isinstance(target, ast.Name) and any(kw in target.id.lower() for kw in ['key', 'secret', 'password', 'token']):
                                if isinstance(node.value, ast.Constant) and isinstance(node.value.value, str):
                                    if len(node.value.value) > 8:
                                        issues.append(f"{py_file.name}:{node.lineno} - Warning: Potential hardcoded credential in '{target.id}'")

                    # 2. Hardcoded Absolute Paths (Python)
                    if isinstance(node, ast.Constant) and isinstance(node.value, str):
                        val = node.value
                        # Matches Windows (C:\...) or Unix-style absolute paths (/usr/...)
                        if re.match(r'^[a-z]:[\\/][^"\'\n]{2,}', val, re.I) or re.match(r'^/[^"\'\n/]{2,}/[^"\'\n/]{2,}', val):
                            if not any(fp in val for fp in ["/dev/null", "/usr/bin/env", "node_modules", ".svg", ".png"]):
                                issues.append(f"{py_file.name}:{node.lineno} - Warning: Potential hardcoded absolute path '{val}'")
        except Exception as e:
            issues.append(f"Error reading {py_file.name}: {str(e)}")
            
    return {"status": "fail" if issues else "pass", "issues": issues}

def _manual_web_lint(path: str) -> List[str]:
    """Scans TSX, TS, and JS files for hardcoded secrets and absolute paths."""
    root = Path(path)
    issues = []
    secret_keywords = ['key', 'secret', 'password', 'token', 'apikey', 'auth']
    
    # Regex for "key": "value" or key = "value" or headers: { "key": "value" }
    secret_pattern = re.compile(r'([\'"]?[\w\-]*(?:' + '|'.join(secret_keywords) + r')[\w\-]*[\'"]?\s*[:=]\s*[\'"])([^\'"]{8,})([\'"])', re.IGNORECASE)
    
    # Regex for hardcoded absolute paths (Windows and Unix)
    path_pattern = re.compile(r'([\'"])([a-z]:[\\/][^"\'\n]{2,}|/[^"\'\n/]{2,}/[^"\'\n/]{2,}[^"\'\n]*)\1', re.IGNORECASE)

    web_extensions = ["*.tsx", "*.ts", "*.js", "*.jsx"]
    files_to_scan = []
    for ext in web_extensions:
        files_to_scan.extend(root.rglob(ext))

    for web_file in files_to_scan:
        # Skip build artifacts and dependencies
        if any(skip in str(web_file) for skip in ["node_modules", ".next", "dist", "build", ".exegol"]):
            continue
            
        try:
            with open(web_file, "r", encoding="utf-8") as f:
                for i, line in enumerate(f, 1):
                    # 1. Check for secrets
                    for match in secret_pattern.finditer(line):
                        # Avoid matching environment variable lookups like process.env.KEY
                        if "process.env" not in line[:match.start()]:
                            issues.append(f"{web_file.relative_to(root)}:{i} - Warning: Potential hardcoded secret in '{match.group(1)}...'")
                    
                    # 2. Check for absolute paths
                    for match in path_pattern.finditer(line):
                        path_val = match.group(2)
                        # Filter false positives
                        if not any(fp in path_val for fp in ["/dev/null", "/usr/bin/env", "node_modules", ".svg", ".png"]):
                             issues.append(f"{web_file.relative_to(root)}:{i} - Warning: Potential hardcoded absolute path '{path_val}'")
        except Exception as e:
            issues.append(f"Error reading {web_file}: {str(e)}")
            
    return issues

if __name__ == "__main__":
    import sys
    target = sys.argv[1] if len(sys.argv) > 1 else os.getcwd()
    res = run_lint(target)
    print(json.dumps(res, indent=2))
