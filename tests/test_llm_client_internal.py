import sys
import os
import json
from typing import Optional, Union

# Add src to path
sys.path.append(os.getcwd())

from src.inference.llm_client import LLMClient

class MockLLMClient(LLMClient):
    """A concrete implementation of LLMClient for testing purposes."""
    def generate(self, prompt: str, system_instruction: Optional[str] = None, json_format: bool = False) -> str:
        return "Mocked response"

class MockAgent:
    """A mock agent for testing system prompt generation."""
    def __init__(self):
        self.name = "TestAgent"
        self.success_metrics = {
            "test_metric": {
                "description": "A metric for testing",
                "target": "100%"
            }
        }
        self.tools = ["tool1", "tool2"]

def test_json_parsing():
    client = MockLLMClient("mock-model")
    
    # Test wrapped JSON
    text1 = "Here is the result: ```json\n{\"status\": \"ok\", \"data\": 123}\n``` Hope this helps."
    parsed1 = client.parse_json_response(text1)
    assert parsed1.get("status") == "ok"
    assert parsed1.get("data") == 123
    
    # Test raw JSON
    text2 = "{\"status\": \"direct\"}"
    parsed2 = client.parse_json_response(text2)
    assert parsed2.get("status") == "direct"
    
    # Test JSON with extra text
    text3 = "Random stuff before {\"key\": \"value\"} random stuff after"
    parsed3 = client.parse_json_response(text3)
    assert parsed3.get("key") == "value"
    
    print("DONE: JSON parsing tests passed")

def test_system_prompt():
    client = MockLLMClient("mock-model")
    agent = MockAgent()
    prompt = client.generate_system_prompt(agent)
    
    assert "TestAgent" in prompt
    assert "A mock agent for testing system prompt generation." in prompt
    assert "test_metric" in prompt
    assert "tool1, tool2" in prompt
    
    print("DONE: System prompt generation tests passed")

if __name__ == "__main__":
    try:
        test_json_parsing()
        test_system_prompt()
        print("\nAll internal verification tests passed!")
    except AssertionError as e:
        print(f"\nVerification failed: {e}")
        sys.exit(1)
    except Exception as e:
        print(f"\nAn error occurred: {e}")
        sys.exit(1)
