import os
import json
import uuid
import pytest
from src.tools.fleet_logger import log_interaction

def test_log_interaction_creates_file():
    # Setup
    repo_path = os.getcwd()
    agent_id = "test_agent"
    outcome = "success"
    task_summary = "Completed a dummy test task"
    session_id = uuid.uuid4().hex
    
    # Execute
    filepath = log_interaction(
        agent_id=agent_id,
        outcome=outcome,
        task_summary=task_summary,
        repo_path=repo_path,
        session_id=session_id
    )
    
    # Verify file exists
    assert os.path.exists(filepath)
    
    # Verify content
    with open(filepath, "r", encoding="utf-8") as f:
        data = json.load(f)
        
    assert data["agent_id"] == agent_id
    assert data["outcome"] == outcome
    assert data["task_summary"] == task_summary
    assert data["session_id"] == session_id
    assert "timestamp" in data
    assert "duration_seconds" in data
    
    # Cleanup (Optional, but good practice for tests)
    # os.remove(filepath)

def test_log_interaction_directory_creation():
    # Setup a fake repo path to test dir creation
    fake_repo = os.path.join(os.getcwd(), "test_temp_repo")
    os.makedirs(fake_repo, exist_ok=True)
    
    try:
        log_interaction(
            agent_id="dir_test",
            outcome="success",
            task_summary="Testing dir creation",
            repo_path=fake_repo
        )
        
        expected_dir = os.path.join(fake_repo, ".exegol", "interaction_logs")
        assert os.path.isdir(expected_dir)
        assert len(os.listdir(expected_dir)) == 1
        
    finally:
        # Cleanup
        import shutil
        shutil.rmtree(fake_repo)

if __name__ == "__main__":
    pytest.main([__file__])
