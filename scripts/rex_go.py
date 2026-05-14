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

from src.agents.research_rex_agent import ResearchRexAgent
from src.handoff import HandoffContext

def run_rex_go():
    print("\n[GO] Initializing Research Rex...")
    
    # Mock LLM Client
    mock_llm = MagicMock()
    mock_llm.generate_system_prompt.return_value = "System prompt"
    
    # Mock analysis data
    analysis_data = {
        "recommendation": "Ollama",
        "reasoning": "Local VRAM is sufficient (12GB). The RTX 5070 provides excellent throughput for Llama-3-8b. Switching to local inference will save ~$50/mo.",
        "hardware_stats": {
            "gpu": "NVIDIA GeForce RTX 5070",
            "vram": "12GB"
        },
        "suggested_actions": [
            "Install llama-3-8b via Ollama: 'ollama pull llama3'",
            "Update model_routing_preference in priority.json to 'ollama'"
        ]
    }
    mock_llm.generate.return_value = json.dumps(analysis_data)
    mock_llm.parse_json_response.return_value = analysis_data
    
    agent = ResearchRexAgent(mock_llm)
    
    repo_path = project_root
    
    handoff = HandoffContext(
        repo_path=repo_path,
        agent_id="research_rex",
        task_id="fleet_cycle", 
        model_routing="mock",
        max_steps=10,
        session_id="go_session_rex",
        scheduled_prompt="go"
    )
    
    print(f"[GO] Executing agent in repo: {repo_path}")
    
    try:
        # We'll allow real state manager calls but mock Slack to avoid spam
        from src.tools.slack_tool import slack_manager
        slack_manager.post_message = MagicMock(return_value="Mock Success")
        
        result = agent.execute(handoff)
        print(f"\n[OK] Execution Result: {result}")
        
        # Verify HITL task creation
        uar_path = os.path.join(repo_path, ".exegol", "user_action_required.json")
        if os.path.exists(uar_path):
            with open(uar_path, 'r') as f:
                queue = json.load(f)
            print(f"\n[VERIFY] Found {len(queue)} HITL tasks in .exegol/user_action_required.json")
            for task in queue:
                if "Inference Setup" in task["task"]:
                    print(f"  - SUCCESS: Verified HITL Task: {task['task']}")
                    
        # Verify report generation
        report_path = os.path.join(repo_path, ".exegol", "research_reports", "inference_strategy.json")
        if os.path.exists(report_path):
            print(f"[VERIFY] Strategy report found at: {report_path}")
            
    except Exception as e:
        import traceback
        print(f"\n[ERROR] Execution Failed: {e}")
        traceback.print_exc()

if __name__ == "__main__":
    run_rex_go()
