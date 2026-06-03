from tools import repo_discovery


def test_sync_discovers_git_and_exegol_repos_only(tmp_path, monkeypatch):
    git_repo = tmp_path / "GitRepo"
    exegol_repo = tmp_path / "ExegolRepo"
    dependency_dir = tmp_path / "node_modules"
    plain_dir = tmp_path / "PlainDir"

    (git_repo / ".git").mkdir(parents=True)
    (exegol_repo / ".exegol").mkdir(parents=True)
    dependency_dir.mkdir()
    plain_dir.mkdir()

    monkeypatch.setattr(repo_discovery, "default_discovery_roots", lambda project_root: [tmp_path])

    config = {"repositories": []}
    added = repo_discovery.sync_discovered_repositories(config, str(tmp_path / "Controller"))

    names = {repo["repo_path"].split("\\")[-1].split("/")[-1] for repo in config["repositories"]}
    assert added == 2
    assert names == {"GitRepo", "ExegolRepo"}


def test_sync_does_not_duplicate_existing_repo(tmp_path, monkeypatch):
    repo = tmp_path / "ExistingRepo"
    (repo / ".git").mkdir(parents=True)
    monkeypatch.setattr(repo_discovery, "default_discovery_roots", lambda project_root: [tmp_path])

    config = {"repositories": [{"repo_path": str(repo.resolve()), "priority": 1}]}

    assert repo_discovery.sync_discovered_repositories(config, str(tmp_path)) == 0
    assert len(config["repositories"]) == 1


def test_register_repository_adds_git_repo_with_defaults(tmp_path):
    repo = tmp_path / "FreshGameRepo"
    (repo / ".git").mkdir(parents=True)
    config = {"repositories": []}

    registered, added = repo_discovery.register_repository(config, str(repo))

    assert added is True
    assert registered["repo_path"] == str(repo.resolve())
    assert registered["agent_status"] == "idle"
    assert registered["model_routing_preference"] == "ollama"
    assert config["repositories"] == [registered]

    existing, added_again = repo_discovery.register_repository(config, str(repo))
    assert added_again is False
    assert existing == registered
    assert len(config["repositories"]) == 1


def test_register_repository_rejects_unmanaged_directory(tmp_path):
    repo = tmp_path / "PlainDir"
    repo.mkdir()

    try:
        repo_discovery.register_repository({"repositories": []}, str(repo))
    except ValueError as exc:
        assert ".git or .exegol" in str(exc)
    else:
        raise AssertionError("Expected unmanaged repo registration to fail")
