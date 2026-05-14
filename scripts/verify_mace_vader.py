import os
import sys
# add src to path
sys.path.append(os.path.join(os.getcwd(), 'src'))
from tools.markdown_formatter import format_markdown
from tools.file_namer import generate_filename

# Path to the pending format file
pending_file = os.path.join(".exegol", "pending_format.txt")

if not os.path.exists(pending_file):
    print(f"Error: {pending_file} not found.")
    sys.exit(1)

with open(pending_file, 'r', encoding='utf-8') as f:
    raw = f.read()

print(f"Read raw text from {pending_file}")

# test namer
name = generate_filename("Messy document for testing")
print(f"Generated name: {name}")

# test formatter
formatted = format_markdown(raw)
print("Formatted output:")
print("---")
print(formatted)
print("---")
