import os

import api


def test_backend_loads_runtime_env_from_repo_root(tmp_path, monkeypatch):
    monkeypatch.delenv("EXEGOL_API_KEY", raising=False)
    (tmp_path / ".env").write_text("EXEGOL_API_KEY=from-temp-env\n", encoding="utf-8")

    api.load_runtime_environment(str(tmp_path))

    assert os.getenv("EXEGOL_API_KEY") == "from-temp-env"
