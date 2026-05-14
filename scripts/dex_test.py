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
from src.agents.developer_dex_agent import DeveloperDexAgent
from src.handoff import HandoffContext

print("[OK] Modules successfully imported.")

def test_dex_execution():
    print("\n[Test] Initializing Developer Dex...")
    
    # Mock LLM Client
    mock_llm = MagicMock()
    # Mock generate_system_prompt if needed by constructor
    mock_llm.generate_system_prompt.return_value = "System prompt"
    
    agent = DeveloperDexAgent(mock_llm)
    
    # Setup Handoff Context
    repo_path = os.getcwd()
    # Using a scheduled prompt with 'sandbox' to trigger _handle_sandbox_request
    handoff = HandoffContext(
        repo_path=repo_path,
        agent_id="developer_dex",
        task_id="test_dex_sandbox",
        model_routing="mock",
        max_steps=5,
        session_id="test_session_dex",
        scheduled_prompt="prototype a sandbox demo app"
    )
    
    print(f"[Test] Executing agent in repo: {repo_path}")
    
    try:
        # Patch slack integration so we don't try to actually post to slack
        with MagicMock() as mock_slack:
            import src.tools.slack_tool
            src.tools.slack_tool.post_to_slack = mock_slack
            
            result = agent.execute(handoff)
            print(f"[OK] Execution Result: {result}")
    except Exception as e:
        print(f"[ERROR] Execution Failed: {e}")

if __name__ == "__main__":
    test_dex_execution()
