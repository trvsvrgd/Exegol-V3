import os
import re
from typing import Optional

def read_file(path: str) -> str:
    """Reads the content of a file."""
    if not os.path.exists(path):
        return f"Error: File not found at {path}"
    with open(path, 'r', encoding='utf-8') as f:
        return f.read()

def write_file(path: str, content: str) -> str:
    """Creates or overwrites a file with the given content."""
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, 'w', encoding='utf-8') as f:
            f.write(content)
        return f"Success: Wrote to {path}"
    except Exception as e:
        return f"Error: {str(e)}"

def replace_content(path: str, old_text: str, new_text: str) -> str:
    """Replaces a specific block of text in a file."""
    content = read_file(path)
    if content.startswith("Error:"):
        return content
    
    if old_text not in content:
        return f"Error: Target text not found in {path}"
    
    new_content = content.replace(old_text, new_text)
    return write_file(path, new_content)

def search_replace_regex(path: str, pattern: str, replacement: str) -> str:
    """Performs a regex search and replace in a file."""
    content = read_file(path)
    if content.startswith("Error:"):
        return content
    
    new_content = re.sub(pattern, replacement, content)
    return write_file(path, new_content)

def delete_file(path: str, reason: str) -> str:
    """Deletes a file, but requires explicit external approval first."""
    if not os.path.exists(path):
        return f"Error: File not found at {path}"
        
    try:
        from tools.slack_tool import request_approval_for_delete
        approval = request_approval_for_delete(path, reason)
        if approval == "APPROVED":
            os.remove(path)
            return f"Success: Deleted {path}"
        else:
            return f"Error: Deletion rejected by user."
    except ImportError:
        return f"Error: Could not import slack_tool to request approval."
    except Exception as e:
        return f"Error: {str(e)}"
