import re
import os

def generate_filename(context: str, extension: str = "md") -> str:
    """Generates a clean, snake_case alphanumeric file name based on document context.
    
    Example: "Weekly Report for April" -> "weekly_report_for_april.md"
    """
    if not context:
        return f"unnamed_file.{extension}"

    # Take the first 7 words
    words = context.split()[:7]
    name = "_".join(words).lower()
    
    # Remove non-alphanumeric (except underscores)
    name = re.sub(r'[^a-z0-9_]', '', name)
    
    # Clean up multiple underscores
    name = re.sub(r'_{2,}', '_', name)
    name = name.strip('_')
    
    if not name:
        name = "document"
        
    return f"{name}.{extension}"
