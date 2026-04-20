import os
import re
from typing import Optional

def read_file(path: str) -> str:
    """Reads the content of a file."""
    if not os.path.exists(path):
        return f"Error: File not found at {path}"
    with open(path, 'r', encoding='utf-8') as f:
        return f.read()

def write_file(path: str, content: str, reason: Optional[str] = None) -> str:
    """Creates or overwrites a file. Requires approval if overwriting a high-risk file."""
    try:
        from tools.safety_gate import get_risk_metadata
        from tools.slack_tool import request_file_approval
        
        # Check if this is an overwrite of a high-risk file
        if os.path.exists(path):
            risk_meta = get_risk_metadata(path)
            if risk_meta["score"] >= 0.7:
                print(f"[FileEditor] High risk overwrite detected for {path}. Requesting approval...")
                approval = request_file_approval(
                    file_path=path,
                    action="OVERWRITE",
                    reason=reason or "System-requested update",
                    risk_score=risk_meta["score"],
                    risk_label=risk_meta["label"],
                    risk_reason=risk_meta["reason"]
                )
                if approval != "APPROVED":
                    return f"Error: Overwrite of {path} rejected by user."

        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, 'w', encoding='utf-8') as f:
            f.write(content)
        return f"Success: Wrote to {path}"
    except Exception as e:
        return f"Error: {str(e)}"

def replace_content(path: str, old_text: str, new_text: str, reason: Optional[str] = None) -> str:
    """Replaces a specific block of text in a file. Requires approval for high-risk files."""
    content = read_file(path)
    if content.startswith("Error:"):
        return content
    
    if old_text not in content:
        return f"Error: Target text not found in {path}"
    
    new_content = content.replace(old_text, new_text)
    # write_file handles the risk check internally for overwrites
    return write_file(path, new_content, reason=reason or f"Replacing content in {os.path.basename(path)}")

def search_replace_regex(path: str, pattern: str, replacement: str, reason: Optional[str] = None) -> str:
    """Performs a regex search and replace in a file. Requires approval for high-risk files."""
    content = read_file(path)
    if content.startswith("Error:"):
        return content
    
    new_content = re.sub(pattern, replacement, content)
    # write_file handles the risk check internally for overwrites
    return write_file(path, new_content, reason=reason or f"Regex replace in {os.path.basename(path)}")

def delete_file(path: str, reason: str) -> str:
    """Deletes a file, but requires explicit external approval first."""
    if not os.path.exists(path):
        return f"Error: File not found at {path}"
        
    try:
        from tools.safety_gate import get_risk_metadata
        from tools.slack_tool import request_file_approval
        
        # Calculate risk before requesting approval
        risk_meta = get_risk_metadata(path)
        
        approval = request_file_approval(
            file_path=path, 
            action="DELETE",
            reason=reason,
            risk_score=risk_meta["score"],
            risk_label=risk_meta["label"],
            risk_reason=risk_meta["reason"]
        )
        
        if approval == "APPROVED":
            os.remove(path)
            return f"Success: Deleted {path} (Risk: {risk_meta['label']})"
        else:
            return f"Error: Deletion rejected by user. Risk was {risk_meta['label']}."
    except ImportError as e:
        return f"Error: Dependency missing for approval: {e}"
    except Exception as e:
        return f"Error: {str(e)}"
