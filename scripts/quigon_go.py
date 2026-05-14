import os
import sys
from unittest.mock import MagicMock

# --- PATH SETUP ---
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
if project_root not in sys.path:
    sys.path.append(project_root)
src_path = os.path.join(project_root, 'src')
if src_path not in sys.path:
    sys.path.append(src_path)

from src.agents.quality_quigon_agent import QualityQuigonAgent
from src.handoff import HandoffContext

def run_quigon_go():
    print("\n[GO] Initializing Quality Quigon...")
    
    # Mock LLM Client
    mock_llm = MagicMock()
    mock_llm.generate_system_prompt.return_value = "System prompt"
    
    agent = QualityQuigonAgent(mock_llm)
    
    repo_path = project_root
    
    handoff = HandoffContext(
        repo_path=repo_path,
        agent_id="quality_quigon",
        task_id="fleet_cycle", # generic task id or something specific?
        model_routing="mock",
        max_steps=15,
        session_id="go_session_quigon",
        scheduled_prompt="go"
    )
    
    print(f"[GO] Executing agent in repo: {repo_path}")
    
    try:
        result = agent.execute(handoff)
        print(f"\n[OK] Execution Result: {result}")
    except Exception as e:
        import traceback
        print(f"\n[ERROR] Execution Failed: {e}")
        traceback.print_exc()

if __name__ == "__main__":
    run_quigon_go()
