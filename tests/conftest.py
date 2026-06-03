import os
import sys

import pytest


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


@pytest.fixture(autouse=True)
def reset_fleet_runtime_stop_state():
    from tools.fleet_runtime_control import resume_runtime

    resume_runtime("pytest setup")
    api_module = sys.modules.get("api")
    if api_module is not None:
        api_module.orchestrator.clear_fleet_stop_request()
    yield
    api_module = sys.modules.get("api")
    if api_module is not None:
        api_module.orchestrator.clear_fleet_stop_request()
    resume_runtime("pytest cleanup")
