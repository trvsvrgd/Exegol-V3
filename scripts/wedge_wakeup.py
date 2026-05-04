import os
import sys
from dotenv import load_dotenv

# Add src to path
sys.path.append(os.path.join(os.getcwd(), 'src'))

from agents.registry import AGENT_REGISTRY
from handoff import HandoffContext
from agents.watcher_wedge_agent import WatcherWedgeAgent

# Mock LLM Client
class MockLLM:
    def generate_system_prompt(self, agent):
        return f"System prompt for {agent.name}"

def main():
    load_dotenv()
    repo_path = os.getcwd()
    
    print("--- Watcher Wedge Manual Wakeup ---")
    
    # Initialize Agent
    llm = MockLLM()
    wedge = WatcherWedgeAgent(llm)
    
    # Create Handoff
    handoff = HandoffContext(
        repo_path=repo_path,
        agent_id="watcher_wedge",
        task_id="manual_test",
        model_routing="mock",
        max_steps=10
    )
    
    # Execute
    result = wedge.execute(handoff)
    print(f"\nResult: {result}")

if __name__ == "__main__":
    main()
