import re

def format_markdown(text: str) -> str:
    """Transforms unstructured or messy text into clean, machine-readable markdown.
    
    Features:
    - Normalizes header spacing (e.g., '#Header' -> '# Header').
    - Ensures single blank line between paragraphs.
    - Fixes common list formatting issues.
    - Trims trailing whitespace.
    """
    if not text:
        return ""

    # 1. Normalize headers (ensure space after #)
    text = re.sub(r'^(#+)([^\s#])', r'\1 \2', text, flags=re.MULTILINE)
    
    # 2. Fix header spacing (ensure blank line before headers, except at start)
    text = re.sub(r'([^\n])\n(#+ )', r'\1\n\n\2', text)
    
    # 3. Trim trailing whitespace on every line
    text = "\n".join([line.rstrip() for line in text.splitlines()])
    
    # 4. Normalize paragraph spacing (max 2 newlines)
    text = re.sub(r'\n{3,}', r'\n\n', text)
    
    # 5. Fix bullet points (ensure space after - or *)
    text = re.sub(r'^([-*])([^\s])', r'\1 \2', text, flags=re.MULTILINE)

    return text.strip() + "\n"
