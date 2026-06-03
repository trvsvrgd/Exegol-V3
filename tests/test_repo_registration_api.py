from fastapi.testclient import TestClient

import api


def test_register_repo_endpoint_persists_new_git_repo(tmp_path, monkeypatch):
    repo = tmp_path / "FreshGameRepo"
    (repo / ".git").mkdir(parents=True)
    saved = []

    api.orchestrator.priority_config = {"repositories": []}
    monkeypatch.setattr(api.orchestrator, "load_config", lambda: None)
    monkeypatch.setattr(api.orchestrator, "save_config", lambda: saved.append(True))
    monkeypatch.setattr(api, "API_KEY", "test-key")

    client = TestClient(api.app)
    response = client.post(
        "/repos/register",
        json={"repo_path": str(repo)},
        headers={"X-API-Key": "test-key"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "added"
    assert body["repo"]["repo_path"] == str(repo.resolve())
    assert saved == [True]
    assert api.orchestrator.priority_config["repositories"][0]["repo_path"] == str(repo.resolve())


def test_register_repo_endpoint_rejects_unmanaged_path(tmp_path, monkeypatch):
    repo = tmp_path / "NotYetARepo"
    repo.mkdir()

    api.orchestrator.priority_config = {"repositories": []}
    monkeypatch.setattr(api.orchestrator, "load_config", lambda: None)
    monkeypatch.setattr(api, "API_KEY", "test-key")

    client = TestClient(api.app)
    response = client.post(
        "/repos/register",
        json={"repo_path": str(repo)},
        headers={"X-API-Key": "test-key"},
    )

    assert response.status_code == 400
    assert ".git or .exegol" in response.json()["detail"]
