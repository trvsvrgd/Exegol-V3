import os
import sys
# add src to path
sys.path.append(os.path.join(os.getcwd(), 'src'))
from tools.markdown_formatter import format_markdown
from tools.file_namer import generate_filename

# test raw text
raw = "#Header\nThis is messy text.*item1"

# test namer
name = generate_filename("Weekly Report for Project Exegol")
print(f"Generated name: {name}")

# test formatter
formatted = format_markdown(raw)
print("Formatted output:")
print(formatted)
