import os
import json
from pathlib import Path
from typing import Dict, List, Any
import jsonschema
from tools.linter import run_lint
from tools.test_runner import run_tests

def validate_app_schema(sandbox_path: str, schema_path: str) -> Dict[str, Any]:
    """
    Validates the app.exegol.json in the sandbox against the master schema using jsonschema.
    """
    app_json_path = Path(sandbox_path) / "app.exegol.json"
    schema_json_path = Path(schema_path)
    
    if not app_json_path.exists():
        return {"status": "fail", "message": "app.exegol.json not found in sandbox"}
    
    if not schema_json_path.exists():
        return {"status": "error", "message": f"Master schema not found at {schema_path}"}

    try:
        with open(app_json_path, "r", encoding="utf-8") as f:
            app_data = json.load(f)
        
        with open(schema_json_path, "r", encoding="utf-8") as f:
            schema_data = json.load(f)
        
        jsonschema.validate(instance=app_data, schema=schema_data)
        return {"status": "pass", "message": "Schema validation successful"}
        
    except jsonschema.exceptions.ValidationError as ve:
        return {
            "status": "fail", 
            "message": f"Schema validation failed: {ve.message}",
            "path": " -> ".join([str(p) for p in ve.path])
        }
    except json.JSONDecodeError as jde:
        return {"status": "error", "message": f"JSON parsing failed: {str(jde)}"}
    except Exception as e:
        return {"status": "error", "message": f"Validation error: {str(e)}"}

def run_sandbox_lint(sandbox_path: str) -> Dict[str, Any]:
    """
    Performs linting checks on the sandbox code using the standardized linter tool.
    """
    return run_lint(sandbox_path)

def run_sandbox_tests(sandbox_path: str) -> Dict[str, Any]:
    """
    Discovers and executes tests within the sandbox using the standardized test_runner tool.
    """
    return run_tests(sandbox_path)

