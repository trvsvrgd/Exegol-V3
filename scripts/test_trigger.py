import os
import sys
import json
from unittest.mock import MagicMock, patch
from datetime import datetime, timedelta

# Add src to path
sys.path.append(os.path.join(os.getcwd(), 'src'))

from orchestrator import ExegolOrchestrator

def test_monthly_trigger():
    print("Testing Monthly Trigger Logic...")
    
    # Setup mock priority.json with an OLD last_run
    old_date = (datetime.now() - timedelta(days=40)).date().isoformat()
    
    with patch('orchestrator.PRIORITY_FILE_PATH', 'config/test_priority.json'):
        # Create test config
        config = {
          "repositories": [
            {
              "repo_path": os.getcwd(),
              "priority": 1,
              "agent_status": "active"
            }
          ],
          "global_settings": {
            "compliance_monitoring": {
              "last_run": old_date,
              "frequency_days": 30
            }
          }
        }
        os.makedirs('config', exist_ok=True)
        with open('config/test_priority.json', 'w') as f:
            json.dump(config, f, indent=2)
            
        orch = ExegolOrchestrator()
        
        # We need to mock wake_and_execute_agent to avoid running the real LLM session
        orch.wake_and_execute_agent = MagicMock()
        orch.wake_and_execute_agent.return_value = MagicMock(outcome="success")
        
        print(f"Triggering fleet cycle with last_run={old_date}...")
        orch.run_fleet_cycle()
        
        # Check if wake_and_execute_agent was called for compliance_cody
        called_with_cody = any(call.kwargs.get('agent_id') == 'compliance_cody' for call in orch.wake_and_execute_agent.call_args_list)
        print(f"Compliance Cody triggered? {called_with_cody}")
        
        # Check if last_run was updated in the file
        with open('config/test_priority.json', 'r') as f:
            new_config = json.load(f)
            new_last_run = new_config['global_settings']['compliance_monitoring']['last_run']
            print(f"New last_run: {new_last_run}")
            
        if called_with_cody and new_last_run == datetime.now().date().isoformat():
            print("Monthly trigger logic VERIFIED.")
        else:
            print("Monthly trigger logic FAILED.")

if __name__ == "__main__":
    test_monthly_trigger()
