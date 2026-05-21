import sys
import os
import pytest

# Add src to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'src')))

from tools.agentic_coding import _extract_json_array, _validate_plan

def test_extract_json_array_direct_list():
    text = '[{"type": "write", "path": "file.txt", "content": "hello"}]'
    res = _extract_json_array(text)
    assert res == [{"type": "write", "path": "file.txt", "content": "hello"}]

def test_extract_json_array_wrapped_list():
    text = '```json\n[{"type": "write", "path": "file.txt", "content": "hello"}]\n```'
    res = _extract_json_array(text)
    assert res == [{"type": "write", "path": "file.txt", "content": "hello"}]

def test_extract_json_array_dict_wrapped():
    text = '{"actions": [{"type": "write", "path": "file.txt", "content": "hello"}]}'
    res = _extract_json_array(text)
    assert res == [{"type": "write", "path": "file.txt", "content": "hello"}]

def test_extract_json_array_single_action_dict():
    text = '{"type": "write", "path": "file.txt", "content": "hello"}'
    res = _extract_json_array(text)
    assert res == [{"type": "write", "path": "file.txt", "content": "hello"}]

def test_extract_json_array_single_action_dict_wrapped():
    text = '```json\n{\n  "type": "write",\n  "path": "file.txt",\n  "content": "hello"\n}\n```'
    res = _extract_json_array(text)
    assert res == [{"type": "write", "path": "file.txt", "content": "hello"}]

def test_validate_plan_aliases():
    actions = [
        {
            "type": "replace",
            "file": "src/tools/secret_manager.py",
            "target": "placeholder",
            "replacement": "my_val"
        }
    ]
    res = _validate_plan(actions)
    assert len(res) == 1
    assert res[0]["path"] == "src/tools/secret_manager.py"
    assert res[0]["content"] == "my_val"

