from tools.interaction_log_reader import read_logs, summarize_logs, get_recent_failures

def read_interaction_logs(repo_path=None, limit=50):
    """Alias for interaction_log_reader.read_logs"""
    return read_logs(repo_path, limit)

def get_log_summary(repo_path=None):
    """Fetches and summarizes logs for a repo."""
    logs = read_logs(repo_path)
    return summarize_logs(logs)
