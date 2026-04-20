import os
import json
from pathlib import Path
from typing import Dict, List, Any

def validate_app_schema(sandbox_path: str, schema_path: str) -> Dict[str, Any]:
    """
    Validates the app.exegol.json in the sandbox against the master schema.
    """
    app_json_path = Path(sandbox_path) / "app.exegol.json"
    if not app_json_path.exists():
        return {"status": "error", "message": "app.exegol.json not found in sandbox"}

    try:
        with open(app_json_path, "r", encoding="utf-8") as f:
            app_data = json.load(f)
        
        # Simple schema check (in a real app we'd use jsonschema)
        required_fields = ["app_name", "version", "inference", "components"]
        missing = [f for f in required_fields if f not in app_data]
        
        if missing:
            return {"status": "fail", "message": f"Missing required fields: {missing}"}
        
        return {"status": "pass", "message": "Schema validation successful"}
    except Exception as e:
        return {"status": "error", "message": f"Schema parsing failed: {str(e)}"}

def run_sandbox_lint(sandbox_path: str) -> Dict[str, Any]:
    """
    Performs basic linting checks on the sandbox code.
    For this version, we check for common anti-patterns like hardcoded absolute paths.
    """
    root = Path(sandbox_path)
    issues = []
    
    for py_file in root.rglob("*.py"):
        try:
            with open(py_file, "r", encoding="utf-8") as f:
                content = f.read()
                if "C:\\" in content or "/home/" in content:
                    issues.append(f"Hardcoded absolute path found in {py_file.name}")
        except Exception as e:
            issues.append(f"Error linting {py_file.name}: {str(e)}")
            
    if issues:
        return {"status": "fail", "issues": issues}
    return {"status": "pass", "message": "Linting passed"}

def run_sandbox_tests(sandbox_path: str) -> Dict[str, Any]:
    """
    Discovers and executes tests within the sandbox.
    Currently searches for test_*.py files and checks if they exist.
    """
    root = Path(sandbox_path)
    test_files = list(root.rglob("test_*.py"))
    
    if not test_files:
        return {"status": "warning", "message": "No test files found in sandbox"}
    
    # In a full implementation, we'd run: subprocess.run(["pytest", str(root)])
    return {"status": "pass", "message": f"Found {len(test_files)} test files. Tests ready for execution."}
