import sys
import os
import json
from unittest.mock import MagicMock

# Add src to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'src')))

import session_manager  # type: ignore
import hmac
import hashlib
from handoff import HandoffContext  # type: ignore
from agents.registry import AGENT_REGISTRY  # type: ignore

def test_agent_spawning_with_llm():
    sm = session_manager.SessionManager(log_every_session=False)
    
    # Mock handoff
    handoff = HandoffContext(
        repo_path=os.getcwd(),
        agent_id="quality_quigon",
        task_id="test_task",
        model_routing="ollama",
        max_steps=15
    )
    
    # Sign handoff
    secret = os.getenv("EXEGOL_HMAC_SECRET", "dev-secret-keep-it-safe")
    data = f"{handoff.repo_path}|{handoff.agent_id}|{handoff.session_id}|{handoff.timestamp}"
    signature = hmac.new(secret.encode(), data.encode(), hashlib.sha256).hexdigest()
    object.__setattr__(handoff, "signature", signature)
    
    # We need to mock the importlib.import_module or just let it run if dependencies are met
    # Let's try to spawn QualityQuigonAgent as it's already updated
    
    registry_entry = AGENT_REGISTRY["quality_quigon"]
    
    print(f"Testing spawn for {registry_entry['class']}...")
    
    # Mocking the actual LLM generation to avoid network calls
    from inference.llm_client import LLMClient  # type: ignore
    LLMClient._generate_ollama = MagicMock(return_value="Mocked response")
    
    result = sm.spawn_agent_session(
        agent_id="quality_quigon",
        module_path=registry_entry["module"],
        class_name=registry_entry["class"],
        handoff=handoff
    )
    
    assert result.outcome == "success"
    print("DONE: Agent spawned and executed successfully.")
    
    # Verify the agent was initialized with an LLMClient and system prompt
    # Since SessionManager deletes the instance, we'd need to instrument the agent or manager to verify.
    # For now, the fact it succeeded implies the __init__ didn't crash.

if __name__ == "__main__":
    try:
        test_agent_spawning_with_llm()
        print("\nIntegration verification passed!")
    except Exception as e:
        print(f"\nIntegration verification failed: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
