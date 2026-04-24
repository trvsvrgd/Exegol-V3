import re
import unicodedata

def sanitize_text(text: str) -> str:
    """
    Strips control characters and normalizes whitespace.
    """
    if not text:
        return ""
    
    # Remove control characters
    text = "".join(ch for ch in text if unicodedata.category(ch)[0] != "C" or ch in "\n\r\t")
    
    # Normalize line endings
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    
    return text.strip()

def detect_prompt_injection(text: str) -> bool:
    """
    Detects common prompt injection markers.
    This is a basic heuristic and not exhaustive.
    """
    injection_patterns = [
        r"ignore previous instructions",
        r"system prompt",
        r"output the full prompt",
        r"forget everything",
        r"you are now a",
        r"instead of your usual role",
        r"bypass",
        r"jailbreak"
    ]
    
    text_lower = text.lower()
    for pattern in injection_patterns:
        if re.search(pattern, text_lower):
            return True
    return False

def sanitize_prompt(text: str) -> dict:
    """
    Sanitizes prompt text and returns a status dictionary.
    """
    sanitized = sanitize_text(text)
    is_injection = detect_prompt_injection(sanitized)
    
    return {
        "sanitized_text": sanitized,
        "is_suspicious": is_injection,
        "warning": "Suspicious pattern detected in input!" if is_injection else None
    }
