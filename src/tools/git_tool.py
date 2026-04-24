import subprocess
import os

def run_git_command(repo_path, args):
    """Executes a git command and returns the output."""
    try:
        result = subprocess.run(
            ["git"] + args,
            cwd=repo_path,
            capture_output=True,
            text=True,
            check=False
        )
        if result.returncode != 0:
            return f"Error: {result.stderr.strip()}"
        return result.stdout.strip()
    except Exception as e:
        return f"Error: {str(e)}"

def has_commits_since(repo_path, timeframe="1 week ago"):
    """Checks if there are any commits since the given timeframe."""
    output = run_git_command(repo_path, ["log", f"--since={timeframe}", "--oneline"])
    if output.startswith("Error:"):
        return False
    return len(output) > 0

def get_recent_commits(repo_path, timeframe="1 week ago"):
    """Returns a list of commit summaries since the given timeframe."""
    output = run_git_command(repo_path, ["log", f"--since={timeframe}", "--oneline"])
    if output.startswith("Error:") or not output:
        return []
    return output.splitlines()

def git_add(repo_path, files=["."]):
    """Stages files for commit."""
    return run_git_command(repo_path, ["add"] + files)

def git_commit(repo_path, message):
    """Commits staged changes with a message."""
    if not message:
        return "Error: Commit message is required."
    return run_git_command(repo_path, ["commit", "-m", message])

def git_push(repo_path, remote="origin", branch=None):
    """Pushes commits to a remote repository."""
    if not branch:
        # Try to get current branch
        branch = run_git_command(repo_path, ["rev-parse", "--abbrev-ref", "HEAD"])
        if branch.startswith("Error:"):
            return branch
    
    return run_git_command(repo_path, ["push", remote, branch])

if __name__ == "__main__":
    # Quick test
    path = os.getcwd()
    print(f"Checking commits in {path}...")
    if has_commits_since(path):
        print("Commits found in the last week:")
        for commit in get_recent_commits(path):
            print(f"  - {commit}")
    else:
        print("No commits found in the last week.")
