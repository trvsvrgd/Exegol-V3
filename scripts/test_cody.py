import os
import sys
import json
from unittest.mock import MagicMock

# Add src to path
sys.path.append(os.path.join(os.getcwd(), 'src'))

from agents.compliance_cody_agent import ComplianceCodyAgent
from handoff import HandoffContext

def test_compliance_cody():
    print("Testing ComplianceCodyAgent...")
    
    # Mock LLM Client
    mock_llm = MagicMock()
    mock_llm.generate_system_prompt.return_value = "You are Cody."
    
    agent = ComplianceCodyAgent(llm_client=mock_llm)
    
    # Setup paths
    repo_path = os.getcwd()
    exegol_dir = os.path.join(repo_path, ".exegol")
    os.makedirs(exegol_dir, exist_ok=True)
    
    # Mock Handoff
    handoff = HandoffContext(
        repo_path=repo_path,
        agent_id="compliance_cody",
        task_id="test_run",
        model_routing="mock",
        max_steps=5
    )
    
    # Run Agent
    result = agent.execute(handoff)
    print(f"Result: {result}")
    
    # Check backlog
    backlog_path = os.path.join(exegol_dir, "backlog.json")
    if os.path.exists(backlog_path):
        with open(backlog_path, 'r') as f:
            backlog = json.load(f)
            print(f"Backlog has {len(backlog)} items.")
            for item in backlog:
                if "Compliance Audit" in item['summary']:
                    print(f"Found compliance task: {item['summary']}")
    
    # Check exceptions
    exception_log = os.path.join(exegol_dir, "compliance_exceptions.log")
    if os.path.exists(exception_log):
        with open(exception_log, 'r') as f:
            content = f.read()
            print("Exception Log Content snippet:")
            print(content[-200:])

if __name__ == "__main__":
    test_compliance_cody()
