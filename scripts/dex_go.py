import os
import sys
import json
from unittest.mock import MagicMock

# --- PATH SETUP ---
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
if project_root not in sys.path:
    sys.path.append(project_root)
src_path = os.path.join(project_root, 'src')
if src_path not in sys.path:
    sys.path.append(src_path)

from src.agents.developer_dex_agent import DeveloperDexAgent
from src.handoff import HandoffContext

def run_dex_go():
    print("\n[GO] Initializing Developer Dex...")
    
    # Mock LLM Client
    mock_llm = MagicMock()
    mock_llm.generate_system_prompt.return_value = "System prompt"
    
    # Mock the generate response to return a valid coding plan array
    coding_plan = [
        {
            "type": "write",
            "path": "scratch/dex_test_output.txt",
            "content": "DeveloperDex successfully executed the task!"
        }
    ]
    mock_llm.generate.return_value = json.dumps(coding_plan)
    # also mock parse_json_response in case it's used
    mock_llm.parse_json_response.return_value = coding_plan
    
    agent = DeveloperDexAgent(mock_llm)
    
    repo_path = project_root
    
    handoff = HandoffContext(
        repo_path=repo_path,
        agent_id="developer_dex",
        task_id="fleet_cycle", 
        model_routing="mock",
        max_steps=15,
        session_id="go_session_dex",
        scheduled_prompt="go"
    )
    
    print(f"[GO] Executing agent in repo: {repo_path}")
    
    try:
        # Patch slack integration
        with MagicMock() as mock_slack:
            import src.tools.slack_tool
            src.tools.slack_tool.post_to_slack = mock_slack
            
            result = agent.execute(handoff)
            print(f"\n[OK] Execution Result: {result}")
    except Exception as e:
        import traceback
        print(f"\n[ERROR] Execution Failed: {e}")
        traceback.print_exc()

if __name__ == "__main__":
    run_dex_go()
