import os
import json
import sys

# Add src to path
sys.path.append(os.path.join(os.path.dirname(__file__), "..", "src"))

from tools.backlog_manager import BacklogManager

def test_backlog_archiving():
    repo_path = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
    bm = BacklogManager(repo_path)
    
    # 1. Setup clean state
    if os.path.exists(bm.backlog_file):
        os.remove(bm.backlog_file)
    if os.path.exists(bm.archive_file):
        os.remove(bm.archive_file)
        
    # 2. Add tasks
    task1 = {"id": "test_001", "summary": "Active task", "status": "todo"}
    task2 = {"id": "test_002", "summary": "Completed task", "status": "completed"}
    
    bm.add_task(task1)
    bm.add_task(task2)
    
    print("Tasks added.")
    
    # 3. Verify backlog state
    backlog = bm.load_backlog()
    assert len(backlog) == 2
    assert any(t["id"] == "test_001" for t in backlog)
    assert any(t["id"] == "test_002" for t in backlog)
    
    # 4. Trigger archival
    archived_count = bm.archive_completed_tasks()
    print(f"Archived {archived_count} tasks.")
    assert archived_count == 1
    
    # 5. Verify final states
    backlog_final = bm.load_backlog()
    archive_final = bm.load_archive()
    
    assert len(backlog_final) == 1
    assert backlog_final[0]["id"] == "test_001"
    
    assert len(archive_final) == 1
    assert archive_final[0]["id"] == "test_002"
    assert "archived_at" in archive_final[0]
    
    print("Verification SUCCESS: Backlog archiving is working correctly!")

if __name__ == "__main__":
    try:
        test_backlog_archiving()
    except AssertionError as e:
        print(f"Verification FAILED: {e}")
        sys.exit(1)
    except Exception as e:
        print(f"An error occurred: {e}")
        sys.exit(1)
