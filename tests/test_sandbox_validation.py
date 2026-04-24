import os
import json
import shutil
import tempfile
import pytest
from src.tools.sandbox_validator import validate_app_schema

@pytest.fixture
def temp_sandbox():
    sandbox_dir = tempfile.mkdtemp()
    yield sandbox_dir
    shutil.rmtree(sandbox_dir)

@pytest.fixture
def master_schema(temp_sandbox):
    schema = {
        "$schema": "http://json-schema.org/draft-07/schema#",
        "type": "object",
        "required": ["app_name", "version", "architecture", "inference", "components"],
        "properties": {
            "app_name": {"type": "string"},
            "version": {"type": "string"},
            "architecture": {"type": "object", "required": ["diagram_type", "source"]},
            "inference": {"type": "object", "required": ["provider", "base_model"]},
            "components": {"type": "array"}
        }
    }
    schema_path = os.path.join(temp_sandbox, "master_schema.json")
    with open(schema_path, "w") as f:
        json.dump(schema, f)
    return schema_path

def test_validate_valid_schema(temp_sandbox, master_schema):
    app_json = {
        "app_name": "Test App",
        "version": "1.0.0",
        "architecture": {"diagram_type": "mermaid", "source": "README.md"},
        "inference": {"provider": "ollama", "base_model": "llama3"},
        "components": []
    }
    with open(os.path.join(temp_sandbox, "app.exegol.json"), "w") as f:
        json.dump(app_json, f)
    
    result = validate_app_schema(temp_sandbox, master_schema)
    assert result["status"] == "pass"

def test_validate_invalid_schema(temp_sandbox, master_schema):
    app_json = {
        "app_name": "Test App",
        # Missing required fields
    }
    with open(os.path.join(temp_sandbox, "app.exegol.json"), "w") as f:
        json.dump(app_json, f)
    
    result = validate_app_schema(temp_sandbox, master_schema)
    assert result["status"] == "fail"
    assert "required" in result["message"].lower()

def test_missing_app_json(temp_sandbox, master_schema):
    result = validate_app_schema(temp_sandbox, master_schema)
    assert result["status"] == "fail"
    assert "not found" in result["message"].lower()
