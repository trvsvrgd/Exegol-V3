import argparse
import json
import os
import sys

from tools.repo_discovery import sync_discovered_repositories

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

    project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    new_repos_count = sync_discovered_repositories(config, project_root)
    
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
