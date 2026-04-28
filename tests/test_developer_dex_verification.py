import sys
import os
import pytest
from unittest.mock import MagicMock

# Add src to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'src')))

from agents.developer_dex_agent import DeveloperDexAgent
from handoff import HandoffContext

def test_developer_dex_initialization():
    """Verify that DeveloperDexAgent can be instantiated and has correct tools."""
    llm_client = MagicMock()
    # Mock system prompt generation
    llm_client.generate_system_prompt.return_value = "Mocked System Prompt"
    
    agent = DeveloperDexAgent(llm_client)
    
    assert agent.name == "DeveloperDexAgent"
    assert "file_editor" in agent.tools
    assert "slack_notifier" in agent.tools
    assert "agentic_coding" in agent.tools
    assert "sandbox_orchestrator" in agent.tools
    print("DONE: DeveloperDexAgent initialization verified.")

def test_developer_dex_coding_cycle_mock():
    """Verify that DeveloperDexAgent can process a coding cycle with a mocked LLM."""
    llm_client = MagicMock()
    llm_client.generate_system_prompt.return_value = "Mocked System Prompt"
    
    # Mock JSON response for planning
    mock_actions = [
        {"type": "write", "path": "tests/temp_test_file.txt", "content": "Hello World"}
    ]
    llm_client.generate.return_value = '```json\n' + str(mock_actions).replace("'", '"') + '\n```'
    llm_client.parse_json_response.return_value = mock_actions
    
    agent = DeveloperDexAgent(llm_client)
    
    # Create handoff
    # Create a temporary directory for the mock repo
    import tempfile
    with tempfile.TemporaryDirectory() as tmp_dir:
        # Create .exegol and active_prompt.md
        exegol_dir = os.path.join(tmp_dir, ".exegol")
        os.makedirs(exegol_dir)
        with open(os.path.join(exegol_dir, "active_prompt.md"), "w") as f:
            f.write("# Active Developer Task\n\nTask for testing.")
            
        handoff = HandoffContext(
            repo_path=tmp_dir,
            agent_id="developer_dex",
            task_id="test_verify_001",
            model_routing="ollama",
            max_steps=5
        )
        
        # Mock file writing to avoid side effects
        from tools import file_editor_tool
        original_write = file_editor_tool.write_file
        file_editor_tool.write_file = MagicMock(return_value="Success")
        
        result = agent.execute(handoff)
        print(f"DEBUG: result is: {result}")
        assert "Coding cycle complete" in result
        assert "Write tests/temp_test_file.txt" in result
        
        # Cleanup
        file_editor_tool.write_file = original_write
        
    print("DONE: DeveloperDexAgent mock coding cycle verified.")

if __name__ == "__main__":
    # Manual run support
    try:
        test_developer_dex_initialization()
        test_developer_dex_coding_cycle_mock()
        print("\nDeveloper Dex verification tests passed!")
    except Exception as e:
        print(f"\nVerification failed: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
