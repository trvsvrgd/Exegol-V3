import os
import sys
import pytest
from unittest.mock import MagicMock

# Add src to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'src')))

from tools.architecture_reviewer import ArchitectureReviewer

def test_architecture_reviewer_mock():
    """Verify that ArchitectureReviewer can be called with a mocked LLM client."""
    mock_client = MagicMock()
    mock_response = '```json\n{"score": 85, "findings": ["Mock finding"], "recommendations": ["Mock recommendation"], "status": "STABLE"}\n```'
    mock_client.generate.return_value = mock_response
    mock_client.parse_json_response.return_value = {
        "score": 85, 
        "findings": ["Mock finding"], 
        "recommendations": ["Mock recommendation"], 
        "status": "STABLE"
    }

    # Use current directory as dummy repo
    repo_path = os.getcwd()
    result = ArchitectureReviewer.review(repo_path, client=mock_client)

    assert result["score"] == 85
    assert "findings" in result
    assert result["status"] == "STABLE"
    
    # Verify generate was called
    assert mock_client.generate.called
    print("DONE: ArchitectureReviewer mock validation verified.")

if __name__ == "__main__":
    test_architecture_reviewer_mock()
