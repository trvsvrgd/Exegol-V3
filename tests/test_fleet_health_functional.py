import os
import sys
import asyncio
import json
import pytest

# Add src to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'src')))

from api import get_fleet_health

@pytest.mark.anyio
async def test_direct_health_call():
    """Call the health endpoint function directly and verify output."""
    print("Executing direct health telemetry audit...")
    try:
        data = await get_fleet_health()
        
        assert isinstance(data, list)
        print(f"Retrieved health metrics for {len(data)} repos.")
        
        for repo in data:
            print(f"Repo: {repo['name']} | Status: {repo['status']} | Backlog: {repo['backlog_count']} | HITL: {repo['hitl_count']}")
            assert "name" in repo
            assert "status" in repo
            assert "backlog_count" in repo
        
        print("\n[QualityQuigon] Telemetry validation PASSED.")
    except Exception as e:
        print(f"\n[QualityQuigon] Telemetry validation FAILED: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

if __name__ == "__main__":
    asyncio.run(test_direct_health_call())
