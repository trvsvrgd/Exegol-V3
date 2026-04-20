import os
import re

def calculate_risk_score(path_str: str) -> float:
    """Calculates a risk score from 0.0 to 1.0 for a given file path."""
    metadata = get_risk_metadata(path_str)
    return metadata["score"]

def get_risk_metadata(path_str: str) -> dict:
    """Analyzes a path and returns score and reason for risk assessment."""
    normalized_path = path_str.replace("\\", "/").lower()
    
    # 1. Critical System Files (Score: 1.0)
    critical_files = [".env", "credentials.json", "token.json", "exegol.bat"]
    if os.path.basename(normalized_path) in critical_files:
        return {
            "score": 1.0,
            "label": "CRITICAL",
            "reason": "This is a core system environment or credential file. Deletion may break system access or security."
        }

    # 2. Core Infrastructure (Score: 0.9)
    if "src/" in normalized_path:
        return {
            "score": 0.9,
            "label": "HIGH",
            "reason": "This file contains core application logic. Deletion will likely cause system failure."
        }
    
    # 3. System Configuration (Score: 0.8)
    if "config/" in normalized_path or normalized_path.endswith("requirements.txt"):
        return {
            "score": 0.8,
            "label": "HIGH",
            "reason": "This file manages system configuration or dependencies. Deletion will impact system stability."
        }

    # 4. Agentic Metadata (Score: 0.7)
    if ".exegol/backlog.json" in normalized_path or ".exegol/vibe_todo.json" in normalized_path:
        return {
            "score": 0.7,
            "label": "MEDIUM-HIGH",
            "reason": "This file tracks project state and tasks. Deletion will cause loss of progress tracking."
        }

    # 5. Tests and Artifacts (Score: 0.2)
    if "tests/" in normalized_path or ".exegol/eval_reports" in normalized_path:
        return {
            "score": 0.2,
            "label": "LOW",
            "reason": "This is a test or evaluation artifact. Deletion is generally safe."
        }
        
    # 6. Default for other files
    return {
        "score": 0.5,
        "label": "MEDIUM",
        "reason": "General project file. Deletion requires standard review."
    }

if __name__ == "__main__":
    # Test cases
    test_paths = [
        "src/agents/developer_dex_agent.py",
        "config/priority.json",
        ".env",
        "tests/test_slack.py",
        "README.md",
        ".exegol/backlog.json"
    ]
    for p in test_paths:
        meta = get_risk_metadata(p)
        print(f"Path: {p:40} | Score: {meta['score']} | Label: {meta['label']:12} | Reason: {meta['reason']}")
