import os
import sys
import json
from unittest.mock import MagicMock

# --- PATH SETUP ---
# Add src to path to resolve the following reported problems:
# - Cannot find module `agents.thoughtful_thrawn_agent`
# - Cannot find module `handoff`
# - Cannot find module `tools.thrawn_intel_manager`
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'src')))

try:
    from agents.thoughtful_thrawn_agent import ThoughtfulThrawnAgent
    from handoff import HandoffContext
    from tools.thrawn_intel_manager import ThrawnIntelManager
    print("[OK] Modules successfully imported.")
except ImportError as e:
    print(f"[ERROR] IMPORT ERROR: {e}")
    print("Check if 'src' directory is in the correct relative location.")
    sys.exit(1)

def test_thrawn_execution():
    """Simple test to verify Thrawn can wake up and read intent."""
    print("\n[Test] Initializing Thoughtful Thrawn...")
    
    # Mock LLM Client
    mock_llm = MagicMock()
    # Mock generate_system_prompt if needed by constructor
    mock_llm.generate_system_prompt.return_value = "System prompt"
    
    agent = ThoughtfulThrawnAgent(mock_llm)
    
    # Setup Handoff Context
    repo_path = os.getcwd()
    handoff = HandoffContext(
        repo_path=repo_path,
        agent_id="thoughtful_thrawn",
        task_id="test_onboarding",
        model_routing="mock",
        max_steps=5,
        session_id="test_session_thrawn"
    )
    
    print(f"[Test] Executing agent in repo: {repo_path}")
    
    # We may need to mock some of the internal tools if they hit real APIs
    with MagicMock() as mock_tool:
        # For this test, we just want to see if it reaches the execute logic
        try:
            result = agent.execute(handoff)
            print(f"[OK] Execution Result: {result}")
        except Exception as e:
            print(f"[ERROR] Execution Failed: {e}")

if __name__ == "__main__":
    test_thrawn_execution()
