import subprocess
import os
import ast
from typing import Dict, Any, List
from pathlib import Path

def run_lint(path: str) -> Dict[str, Any]:
    """
    Performs linting on the specified directory.
    Uses 'pylint' if available, otherwise falls back to AST-based static analysis.
    """
    if not os.path.exists(path):
        return {"status": "error", "message": f"Path not found: {path}"}
    
    results = {
        "status": "pass",
        "issues": [],
        "message": "Linting complete"
    }
    
    # Try to use pylint if available
    try:
        # Check if pylint is installed
        subprocess.run(["pylint", "--version"], capture_output=True, check=True)
        print(f"[linter] Running pylint on {path}...")
        res = subprocess.run(
            ["pylint", path, "--output-format=json"],
            capture_output=True,
            text=True
        )
        # Pylint exit code is a bitmask, 0 means no issues
        if res.returncode != 0:
            try:
                pylint_issues = json.loads(res.stdout)
                for issue in pylint_issues:
                    results["issues"].append(f"{issue['path']}:{issue['line']} - {issue['message']}")
                results["status"] = "fail"
            except:
                # Fallback if JSON parsing fails
                if res.stdout:
                     results["issues"].append(res.stdout)
                     results["status"] = "fail"
        return results
    except (subprocess.CalledProcessError, FileNotFoundError):
        # Fallback to manual AST check
        print(f"[linter] pylint not found. Falling back to AST-based check on {path}...")
        return _manual_ast_lint(path)

def _manual_ast_lint(path: str) -> Dict[str, Any]:
    root = Path(path)
    issues = []
    
    for py_file in root.rglob("*.py"):
        try:
            with open(py_file, "r", encoding="utf-8") as f:
                content = f.read()
                
                # 1. Syntax check
                try:
                    tree = ast.parse(content)
                except SyntaxError as se:
                    issues.append(f"{py_file.name}:{se.lineno} - Syntax Error: {se.msg}")
                    continue
                
                # 2. Basic static analysis via AST
                for node in ast.walk(tree):
                    # Check for print statements (optional, but good for debt)
                    # if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == 'print':
                    #     issues.append(f"{py_file.name}:{node.lineno} - Info: print() call found")
                    
                    # Check for hardcoded credentials (very basic)
                    if isinstance(node, ast.Assign):
                        for target in node.targets:
                            if isinstance(target, ast.Name) and any(kw in target.id.lower() for kw in ['key', 'secret', 'password', 'token']):
                                if isinstance(node.value, ast.Constant) and isinstance(node.value.value, str):
                                    if len(node.value.value) > 8: # Arbitrary length to avoid short strings
                                        issues.append(f"{py_file.name}:{node.lineno} - Warning: Potential hardcoded credential in '{target.id}'")

        except Exception as e:
            issues.append(f"Error reading {py_file.name}: {str(e)}")
            
    if issues:
        return {"status": "fail", "issues": issues, "message": f"Found {len(issues)} issues"}
    return {"status": "pass", "message": "AST-based linting passed"}

if __name__ == "__main__":
    import sys
    target = sys.argv[1] if len(sys.argv) > 1 else os.getcwd()
    res = run_lint(target)
    print(f"Status: {res['status']}")
    for issue in res.get('issues', []):
        print(f" - {issue}")
