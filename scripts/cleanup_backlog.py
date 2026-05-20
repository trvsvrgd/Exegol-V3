import os
import sys
import json

# Add src/ directory to python path
sys.path.append(os.path.join(os.path.dirname(os.path.dirname(__file__)), "src"))

from tools.backlog_manager import BacklogManager

def run_cleanup():
    priority_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "config", "priority.json")
    if not os.path.exists(priority_path):
        print(f"Error: priority.json not found at {priority_path}")
        sys.exit(1)

    try:
        with open(priority_path, "r", encoding="utf-8") as f:
            config = json.load(f)
    except Exception as e:
        print(f"Error reading priority.json: {e}")
        sys.exit(1)

    repositories = config.get("repositories", [])
    if not repositories:
        print("No repositories configured.")
        return

    print("Starting automated backlog cleanup and task archiving...")
    for repo in repositories:
        repo_path = repo.get("repo_path")
        if not repo_path:
            continue
        
        if not os.path.exists(repo_path):
            print(f"Skipping non-existent repository path: {repo_path}")
            continue

        print(f"\nProcessing repository: {repo_path}")
        try:
            bm = BacklogManager(repo_path)
            archived = bm.archive_completed_tasks()
            print(f"Successfully archived {archived} completed/done task(s).")
        except Exception as e:
            print(f"Failed to cleanup backlog for {repo_path}: {e}")

if __name__ == "__main__":
    run_cleanup()
