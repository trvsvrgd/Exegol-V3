import os
import json
import sys
import tempfile

# Add src to path
sys.path.append(os.path.join(os.path.dirname(__file__), "..", "src"))

from tools.backlog_manager import BacklogManager

def test_backlog_archiving():
    # Use a temp directory so each test run starts with a clean SQLite DB
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp_dir:
        import os as _os
        _os.makedirs(_os.path.join(tmp_dir, ".exegol"), exist_ok=True)
        bm = BacklogManager(tmp_dir)

        # 2. Add tasks
        task1 = {"id": "test_001", "summary": "Active task", "status": "todo"}
        task2 = {"id": "test_002", "summary": "Completed task", "status": "completed"}
        
        bm.add_task(task1)
        bm.add_task(task2)
        
        print("Tasks added.")
        
        # 3. Verify backlog state (both are non-archived at this point)
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


def test_backlog_dedupe_auto_failures_archives_repeated_rows(tmp_path):
    bm = BacklogManager(str(tmp_path))
    first = {
        "id": "auto_fail_DeveloperDexAgent_1",
        "summary": "FIX: DeveloperDexAgent autonomous failure",
        "priority": "high",
        "status": "todo",
        "created_at": "2026-05-01T00:00:00",
    }
    duplicate = {
        "id": "auto_fail_DeveloperDexAgent_2",
        "summary": "FIX: DeveloperDexAgent autonomous failure",
        "priority": "high",
        "status": "todo",
        "created_at": "2026-05-02T00:00:00",
    }
    distinct = {
        "id": "manual_task",
        "summary": "Implement a separate feature",
        "priority": "medium",
        "status": "todo",
        "created_at": "2026-05-03T00:00:00",
    }

    assert bm.add_task(first)
    assert bm.add_task(duplicate)
    assert bm.add_task(distinct)

    result = bm.dedupe_auto_failures()

    assert result["removed_duplicates"] == 1
    active_ids = {task["id"] for task in bm.load_backlog()}
    assert active_ids == {"auto_fail_DeveloperDexAgent_1", "manual_task"}
    canonical = bm.get_task("auto_fail_DeveloperDexAgent_1")
    archived = bm.get_task("auto_fail_DeveloperDexAgent_2")
    assert canonical["merged_duplicate_ids"] == ["auto_fail_DeveloperDexAgent_2"]
    assert archived["canonical_task_id"] == "auto_fail_DeveloperDexAgent_1"


def test_archive_task_archives_arbitrary_row_with_reason(tmp_path):
    bm = BacklogManager(str(tmp_path))
    assert bm.add_task({
        "id": "stale_generated_report",
        "summary": "Generated report with no actionable evidence",
        "priority": "high",
        "status": "todo",
        "created_at": "2026-05-01T00:00:00",
    })

    archived = bm.archive_task(
        "stale_generated_report",
        reason="Stale generated backlog row after verification",
        final_status="done",
        updates={"resolution": "No actionable evidence remained."},
    )

    assert archived is True
    assert bm.load_backlog() == []
    archive = bm.load_archive()
    assert len(archive) == 1
    assert archive[0]["id"] == "stale_generated_report"
    assert archive[0]["status"] == "done"
    assert archive[0]["archive_reason"] == "Stale generated backlog row after verification"
    assert archive[0]["resolution"] == "No actionable evidence remained."


if __name__ == "__main__":
    try:
        test_backlog_archiving()
    except AssertionError as e:
        print(f"Verification FAILED: {e}")
        sys.exit(1)
    except Exception as e:
        print(f"An error occurred: {e}")
        sys.exit(1)
