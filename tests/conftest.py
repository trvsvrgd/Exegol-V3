import os
import sys


ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
SRC = os.path.join(ROOT, "src")

for path in (ROOT, SRC):
    if path not in sys.path:
        sys.path.insert(0, path)

test_tmp = os.path.join(ROOT, ".pytest_tmp", "tempfile")
os.makedirs(test_tmp, exist_ok=True)
os.environ.setdefault("TMP", test_tmp)
os.environ.setdefault("TEMP", test_tmp)
os.environ.setdefault("TMPDIR", test_tmp)
os.environ.setdefault("EXEGOL_DISABLE_SCHEDULER_FOR_TESTS", "1")
