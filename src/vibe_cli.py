import argparse
import json
import os
import sys

PRIORITY_FILE_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'config', 'priority.json')

def load_config():
    if os.path.exists(PRIORITY_FILE_PATH):
        try:
            with open(PRIORITY_FILE_PATH, 'r') as f:
                return json.load(f)
        except json.JSONDecodeError:
            print(f"Error: Could not parse JSON from {PRIORITY_FILE_PATH}", file=sys.stderr)
            sys.exit(1)
    print(f"Error: Configuration file not found at {PRIORITY_FILE_PATH}", file=sys.stderr)
    sys.exit(1)

def save_config(config):
    with open(PRIORITY_FILE_PATH, 'w') as f:
        json.dump(config, f, indent=2)

def sync_repositories():
    config = load_config()
    if "repositories" not in config:
        config["repositories"] = []
    
    existing_paths = {repo.get("repo_path") for repo in config.get("repositories", [])}
    
    # Exegol_v3 is at: <workspace>\src\vibe_cli.py
    # Parent is the workspace folder, and we want its parent.
    # Actually, the user's workspace is c:\Users\travi\Documents\Python_Projects\Exegol_v3
    # We want to scan c:\Users\travi\Documents\Python_Projects
    current_script_dir = os.path.dirname(os.path.abspath(__file__))
    project_root = os.path.dirname(current_script_dir)
    parent_dir = os.path.dirname(project_root)
    
    print(f"Scanning directory: {parent_dir}")
    
    ignore_list = {
        "node_modules", "node-modules", "zzArchive", ".venv", ".git", ".gemini", 
        "__pycache__", "context-portfolio", "n8n", "OpenShell"
    }
    
    new_repos_count = 0
    for item in os.listdir(parent_dir):
        item_path = os.path.join(parent_dir, item)
        if os.path.isdir(item_path) and item not in ignore_list and not item.startswith('.'):
            # Use absolute path for consistency
            normalized_path = os.path.abspath(item_path)
            if normalized_path not in existing_paths:
                new_repo = {
                    "repo_path": normalized_path,
                    "priority": 10,
                    "model_routing_preference": "ollama",
                    "agent_status": "idle",
                    "max_steps_policy": 50,
                    "requires_slack_approval_for_deletes": True,
                    "daily_commit_routine": True
                }
                config["repositories"].append(new_repo)
                existing_paths.add(normalized_path)
                print(f"Discovered new repository: {item}")
                new_repos_count += 1
    
    if new_repos_count > 0:
        save_config(config)
        print(f"Sync complete. Added {new_repos_count} new repositories.")
    else:
        print("Sync complete. No new repositories discovered.")


def set_priority(repo_name, priority):
    config = load_config()
    repos = config.get("repositories", [])
    found = False
    
    for repo in repos:
        # Check if repo_name matches exactly or is a substring of the path
        if repo_name == repo.get("repo_path") or repo_name == os.path.basename(repo.get("repo_path", "")):
            repo["priority"] = priority
            found = True
            print(f"Matched repository '{repo['repo_path']}'.")
            break
            
    if not found:
        # Fallback to substring matching if exact/basename match fails
        for repo in repos:
            if repo_name in repo.get("repo_path", ""):
                repo["priority"] = priority
                found = True
                print(f"Matched repository '{repo['repo_path']}' by substring.")
                break
                
    if found:
        save_config(config)
        print(f"Successfully set priority to {priority}.")
    else:
        print(f"Error: Repository matching '{repo_name}' not found.", file=sys.stderr)

def main():
    parser = argparse.ArgumentParser(description="Exegol V3 CLI")
    subparsers = parser.add_subparsers(dest="command", required=True)
    
    set_parser = subparsers.add_parser("set", help="Set the priority of a repository")
    set_parser.add_argument("repo_name", type=str, help="Name or path substring of the repository")
    set_parser.add_argument("priority_score", type=int, help="Priority score to assign (lower is higher priority)")
    
    subparsers.add_parser("sync", help="Discover neighboring repositories and add them to the config")
    
    args = parser.parse_args()
    
    if args.command == "set":
        set_priority(args.repo_name, args.priority_score)
    elif args.command == "sync":
        sync_repositories()

if __name__ == "__main__":
    main()
