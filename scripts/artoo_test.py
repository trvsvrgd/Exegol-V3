import os
import sys
from unittest.mock import MagicMock

# --- PATH SETUP ---
# Add project root to path so we can import from 'src'
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
if project_root not in sys.path:
    sys.path.append(project_root)
src_path = os.path.join(project_root, 'src')
if src_path not in sys.path:
    sys.path.append(src_path)

# Standard imports using the 'src' package prefix
from src.agents.architect_artoo_agent import ArchitectArtooAgent
from src.handoff import HandoffContext

print("[OK] Modules successfully imported.")

def test_artoo_execution():
    print("\n[Test] Initializing Architect Artoo...")
    
    # Mock LLM Client
    mock_llm = MagicMock()
    # Mock generate_system_prompt if needed by constructor
    mock_llm.generate_system_prompt.return_value = "System prompt"
    
    agent = ArchitectArtooAgent(mock_llm)
    
    # Setup Handoff Context
    repo_path = os.getcwd()
    # Adding 'analyze' in scheduled_prompt to force it to wake up
    handoff = HandoffContext(
        repo_path=repo_path,
        agent_id="architect_artoo",
        task_id="test_architecture",
        model_routing="mock",
        max_steps=5,
        session_id="test_session_artoo",
        scheduled_prompt="analyze"
    )
    
    print(f"[Test] Executing agent in repo: {repo_path}")
    
    try:
        result = agent.execute(handoff)
        print(f"[OK] Execution Result: {result}")
    except Exception as e:
        print(f"[ERROR] Execution Failed: {e}")

if __name__ == "__main__":
    test_artoo_execution()
