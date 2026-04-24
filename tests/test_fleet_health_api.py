import os
import sys
import pytest
from fastapi.testclient import TestClient

# Add src to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'src')))

from api import app

client = TestClient(app)

def test_get_fleet_health():
    """Verify that the /fleet/health endpoint returns data for the active repos."""
    # Note: This requires the environment to have EXEGOL_API_KEY or use the default
    api_key = os.getenv("EXEGOL_API_KEY", "dev-local-key")
    
    response = client.get("/fleet/health", headers={"X-API-Key": api_key})
    
    assert response.status_code == 200
    data = response.json()
    
    assert isinstance(data, list)
    if len(data) > 0:
        repo = data[0]
        assert "name" in repo
        assert "path" in repo
        assert "status" in repo
        assert "backlog_count" in repo
        assert "hitl_count" in repo
        
        # Verify the name matches the expected repo name (Exegol_v3)
        assert repo["name"] == "Exegol_v3"
        print(f"Verified health metrics for {repo['name']}")

if __name__ == "__main__":
    test_get_fleet_health()
