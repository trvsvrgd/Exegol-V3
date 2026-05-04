import os
import json
import datetime
from typing import List, Dict, Any

def calculate_risk_score(proposed_changes: List[Dict[str, Any]], repo_path: str) -> Dict[str, Any]:
    """Calculates a risk score for a set of proposed changes based on file sensitivity and impact.
    
    Risk Factors:
    - Suffix sensitivity (.env, .py, .js vs .md, .txt)
    - Directory sensitivity (src/agents, src/tools, config vs tests, scratch)
    - Number of files changed
    - Presence of critical keywords (secrets, auth, encryption, database)
    """
    total_score = 0.0
    findings = []
    
    sensitivity_map = {
        ".env": 10.0,
        "credentials.json": 10.0,
        "config": 5.0,
        "src/agents": 8.0,
        "src/tools": 7.0,
        "tests": 1.0,
        "README.md": 0.1,
        ".exegol": 4.0
    }
    
    critical_keywords = ["secret", "password", "token", "auth", "encrypt", "decrypt", "db.", "connection_string"]
    
    for change in proposed_changes:
        path = change.get("path", "")
        content = change.get("content", "")
        file_score = 1.0 # Base score
        
        # 1. Path-based risk
        for sensitivity_path, weight in sensitivity_map.items():
            if sensitivity_path in path:
                file_score *= weight
                findings.append(f"High sensitivity path detected: {path} (Weight: {weight})")
                break
        
        # 2. Content-based risk
        keyword_count = 0
        for kw in critical_keywords:
            if kw in content.lower():
                keyword_count += 1
        
        if keyword_count > 0:
            file_score *= (1.0 + (0.5 * keyword_count))
            findings.append(f"Critical keywords found in {path}: {keyword_count} instances")
            
        total_score += file_score

    # Normalize score
    # 0-5: Low, 5-15: Medium, 15-50: High, 50+: Critical
    risk_level = "low"
    if total_score > 50: risk_level = "critical"
    elif total_score > 15: risk_level = "high"
    elif total_score > 5: risk_level = "medium"
    
    return {
        "score": round(total_score, 2),
        "level": risk_level,
        "findings": findings,
        "timestamp": datetime.datetime.now().isoformat()
    }

if __name__ == "__main__":
    # Example usage
    sample_changes = [
        {"path": "src/agents/developer_dex_agent.py", "content": "import secrets; key = secrets.token_hex(16)"},
        {"path": "README.md", "content": "Updated documentation"}
    ]
    print(json.dumps(calculate_risk_score(sample_changes, "."), indent=2))
